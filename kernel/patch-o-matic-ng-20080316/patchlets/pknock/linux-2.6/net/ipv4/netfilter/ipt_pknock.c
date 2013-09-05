/*
 * Kernel module to implement Port Knocking and SPA matching support.
 *
 * (C) 2006-2008 J. Federico Hernandez Scarso <fede.hernandez@gmail.com>
 * (C) 2006 Luis A. Floreani <luis.floreani@gmail.com>
 *
 * $Id: ipt_pknock.c 437 2008-01-12 19:05:17Z fender $
 *
 * This program is released under the terms of GNU GPL version 2.
 */
#include <linux/module.h>
#include <linux/version.h>
#include <linux/skbuff.h>
#include <linux/ip.h>
#include <linux/tcp.h>
#include <linux/udp.h>
#include <linux/in.h>
#include <linux/list.h>
#include <linux/proc_fs.h>
#include <linux/spinlock.h>
#include <linux/jhash.h>
#include <linux/random.h>
#include <linux/crypto.h>
#include <linux/scatterlist.h>
#include <linux/jiffies.h>
#include <linux/timer.h>
#include <linux/seq_file.h>
#include <linux/connector.h>

#include <linux/netfilter/x_tables.h>
#include <linux/netfilter_ipv4/ipt_pknock.h>

MODULE_AUTHOR("J. Federico Hernandez Scarso, Luis A. Floreani");
MODULE_DESCRIPTION("netfilter match for Port Knocking and SPA");
MODULE_LICENSE("GPL");

enum {
	GC_EXPIRATION_TIME 	= 65000, /* in msecs */
	DEFAULT_RULE_HASH_SIZE  = 8,
	DEFAULT_PEER_HASH_SIZE  = 16,
};

#define hashtable_for_each_safe(pos, n, head, size, i)		\
	for ((i) = 0; (i) < (size); (i)++)			\
		list_for_each_safe((pos), (n), (&head[(i)]))

#if DEBUG
	#define DEBUGP(msg, peer) printk(KERN_INFO MOD		\
			"(S) peer: %u.%u.%u.%u - %s.\n",	\
			NIPQUAD((peer)->ip), msg)
	#define duprintf(format, args...) printk(format, ## args);
#else
	#define DEBUGP(msg, peer)
	#define duprintf(format, args...)
#endif

static u_int32_t ipt_pknock_hash_rnd;

static unsigned int rule_hashsize		= DEFAULT_RULE_HASH_SIZE;
static unsigned int peer_hashsize		= DEFAULT_PEER_HASH_SIZE;
static unsigned int ipt_pknock_gc_expir_time	= GC_EXPIRATION_TIME;
static int nl_multicast_group			= -1;

static struct list_head *rule_hashtable		= NULL;
static struct proc_dir_entry *pde		= NULL;

static DEFINE_SPINLOCK(list_lock);

static struct ipt_pknock_crypto crypto = {
	.algo	= "hmac(sha256)",
	.tfm	= NULL,
	.size	= 0
};

module_param(rule_hashsize, int, S_IRUGO);
module_param(peer_hashsize, int, S_IRUGO);
module_param(ipt_pknock_gc_expir_time, int, S_IRUGO);
module_param(nl_multicast_group, int, S_IRUGO);

/**
 * Calculates a value from 0 to max from a hash of the arguments.
 *
 * @key
 * @len: length
 * @initval
 * @max
 * @return: a 32 bits index
 */
static u_int32_t
pknock_hash(const void *key, u_int32_t len, u_int32_t initval, u_int32_t max)
{
	return jhash(key, len, initval) % max;
}

/**
 * @return: the epoch minute
 */
static int
get_epoch_minute(void)
{
	struct timespec t = CURRENT_TIME;
	return (int)(t.tv_sec/60);
}

/**
 * Alloc a hashtable with n buckets.
 *
 * @size
 * @return: hashtable
 */
static struct list_head *
alloc_hashtable(int size)
{
	struct list_head *hash = NULL;
	unsigned int i;

	if ((hash = kmalloc(sizeof(*hash) * size, GFP_ATOMIC)) == NULL) {
		printk(KERN_ERR MOD "kmalloc() error in alloc_hashtable() "
                        "function.\n");
		return NULL;
	}

	for (i = 0; i < size; i++)
		INIT_LIST_HEAD(&hash[i]);

	return hash;
}

/**
 * This function converts the status from integer to string.
 *
 * @status
 * @return: status
 */
static inline const char *
status_itoa(enum status status)
{
	switch (status) {
		case ST_INIT: 	  return "INIT";
		case ST_MATCHING: return "MATCHING";
		case ST_ALLOWED:  return "ALLOWED";
	}
	return "UNKNOWN";
}

/**
 * @s
 * @pos
 * @return: private value used by the iterator
 */
static void *
pknock_seq_start(struct seq_file *s, loff_t *pos)
{
	struct proc_dir_entry *pde = s->private;
	struct ipt_pknock_rule *rule = pde->data;

	spin_lock_bh(&list_lock);

	if (*pos >= peer_hashsize)
		return NULL;

	return rule->peer_head + *pos;
}

/**
 * @s
 * @v
 * @pos
 * @return: next value for the iterator
 */
static void *
pknock_seq_next(struct seq_file *s, void *v, loff_t *pos)
{
	struct proc_dir_entry *pde = s->private;
	struct ipt_pknock_rule *rule = pde->data;

	(*pos)++;
	if (*pos >= peer_hashsize)
		return NULL;

	return rule->peer_head + *pos;
}

/**
 * @s
 * @v
 */
static void
pknock_seq_stop(struct seq_file *s, void *v)
{
	spin_unlock_bh(&list_lock);
}

/**
 * @s
 * @v
 * @return: 0 if OK
 */
static int
pknock_seq_show(struct seq_file *s, void *v)
{
	struct list_head *pos = NULL, *n = NULL;
	struct peer *peer = NULL;
	unsigned long expir_time = 0;
        u_int32_t ip;

	struct list_head *peer_head = (struct list_head *)v;

	struct proc_dir_entry *pde = s->private;
	struct ipt_pknock_rule *rule = pde->data;

	list_for_each_safe(pos, n, peer_head) {
		peer = list_entry(pos, struct peer, head);
		ip = htonl(peer->ip);
		expir_time = time_before(jiffies/HZ,
                                        peer->timestamp + rule->max_time)
			? ((peer->timestamp + rule->max_time)-(jiffies/HZ)) : 0;

		seq_printf(s, "src=%u.%u.%u.%u ", NIPQUAD(ip));
		seq_printf(s, "proto=%s ", (peer->proto == IPPROTO_TCP) ?
                                                "TCP" : "UDP");
		seq_printf(s, "status=%s ", status_itoa(peer->status));
		seq_printf(s, "expir_time=%ld ", expir_time);
		seq_printf(s, "next_port_id=%d ", peer->id_port_knocked-1);
		seq_printf(s, "\n");
	}

	return 0;
}

static struct seq_operations pknock_seq_ops = {
	.start = pknock_seq_start,
	.next = pknock_seq_next,
	.stop = pknock_seq_stop,
	.show = pknock_seq_show
};

/**
 * @inode
 * @file
 */
static int
pknock_proc_open(struct inode *inode, struct file *file)
{
	int ret = seq_open(file, &pknock_seq_ops);
	if (!ret) {
		struct seq_file *sf = file->private_data;
		sf->private = PDE(inode);
	}
	return ret;
}

static struct file_operations pknock_proc_ops = {
	.owner = THIS_MODULE,
	.open = pknock_proc_open,
	.read = seq_read,
	.llseek = seq_lseek,
	.release = seq_release
};

/**
 * It updates the rule timer to execute garbage collector.
 *
 * @rule
 */
static inline void
update_rule_timer(struct ipt_pknock_rule *rule)
{
	if (timer_pending(&rule->timer))
		del_timer(&rule->timer);

	rule->timer.expires = jiffies +
                                msecs_to_jiffies(ipt_pknock_gc_expir_time);
	add_timer(&rule->timer);
}

/**
 * @peer
 * @max_time
 * @return: 1 time exceeded, 0 still valid
 */
static inline bool
is_time_exceeded(struct peer *peer, int max_time)
{
	return peer && time_after(jiffies/HZ, peer->timestamp + max_time);
}

/**
 * @peer
 * @return: 1 has logged, 0 otherwise
 */
static inline bool
has_logged_during_this_minute(const struct peer *peer)
{
	return peer && (peer->login_min == get_epoch_minute());
}

/**
 * Garbage collector. It removes the old entries after timer has expired.
 *
 * @r: rule
 */
static void
peer_gc(unsigned long r)
{
	int i;
	struct ipt_pknock_rule *rule = (struct ipt_pknock_rule *)r;
	struct peer *peer = NULL;
	struct list_head *pos = NULL, *n = NULL;

	hashtable_for_each_safe(pos, n, rule->peer_head, peer_hashsize, i) {
		peer = list_entry(pos, struct peer, head);
		if (!has_logged_during_this_minute(peer)
                        && is_time_exceeded(peer, rule->max_time)) 
		{
                        DEBUGP("DESTROYED", peer);
			list_del(pos);
			kfree(peer);
		}
	}
}

/**
 * Compares length and name equality for the rules.
 *
 * @info
 * @rule
 * @return: 0 equals, 1 otherwise
 */
static inline int
rulecmp(const struct ipt_pknock_info *info, const struct ipt_pknock_rule *rule)
{
	if (info->rule_name_len != rule->rule_name_len)
		return 1;
	if (strncmp(info->rule_name, rule->rule_name, info->rule_name_len) != 0)
		return 1;
	return 0;
}

/**
 * Search the rule and returns a pointer if it exists.
 *
 * @info
 * @return: rule or NULL
 */
static inline struct ipt_pknock_rule *
search_rule(const struct ipt_pknock_info *info)
{
	struct ipt_pknock_rule *rule = NULL;
	struct list_head *pos = NULL, *n = NULL;
	int hash = pknock_hash(info->rule_name, info->rule_name_len,
                                ipt_pknock_hash_rnd, rule_hashsize);

	list_for_each_safe(pos, n, &rule_hashtable[hash]) {
		rule = list_entry(pos, struct ipt_pknock_rule, head);
		if (rulecmp(info, rule) == 0)
			return rule;
	}
	return NULL;
}

/**
 * It adds a rule to list only if it doesn't exist.
 *
 * @info
 * @return: 1 success, 0 failure
 */
static bool
add_rule(struct ipt_pknock_info *info)
{
	struct ipt_pknock_rule *rule = NULL;
	struct list_head *pos = NULL, *n = NULL;
	int hash = pknock_hash(info->rule_name, info->rule_name_len,
                                ipt_pknock_hash_rnd, rule_hashsize);

	list_for_each_safe(pos, n, &rule_hashtable[hash]) {
		rule = list_entry(pos, struct ipt_pknock_rule, head);

		if (rulecmp(info, rule) == 0) {
			rule->ref_count++;
#if DEBUG
			if (info->option & IPT_PKNOCK_CHECKIP) {
				printk(KERN_DEBUG MOD "add_rule() (AC)"
					" rule found: %s - "
					"ref_count: %d\n",
					rule->rule_name,
					rule->ref_count);
			}
#endif
			return true;
		}
	}

	if ((rule = kmalloc(sizeof (*rule), GFP_ATOMIC)) == NULL) {
		printk(KERN_ERR MOD "kmalloc() error in add_rule().\n");
		return false;
	}

	INIT_LIST_HEAD(&rule->head);

	memset(rule->rule_name, 0, IPT_PKNOCK_MAX_BUF_LEN + 1);
	strncpy(rule->rule_name, info->rule_name, info->rule_name_len);
	rule->rule_name_len = info->rule_name_len;

	rule->ref_count	= 1;
	rule->max_time	= info->max_time;

	if (!(rule->peer_head = alloc_hashtable(peer_hashsize))) {
		printk(KERN_ERR MOD "alloc_hashtable() error in add_rule().\n");
		return false;
	}

	init_timer(&rule->timer);
	rule->timer.function	= peer_gc;
	rule->timer.data	= (unsigned long)rule;

	rule->status_proc = create_proc_entry(info->rule_name, 0, pde);
	if (!rule->status_proc) {
		printk(KERN_ERR MOD "create_proc_entry() error in add_rule()"
                        " function.\n");
                kfree(rule);
                return false;
	}

	rule->status_proc->proc_fops = &pknock_proc_ops;
	rule->status_proc->data = rule;

	list_add(&rule->head, &rule_hashtable[hash]);
#if DEBUG
	printk(KERN_INFO MOD "(A) rule_name: %s - created.\n", rule->rule_name);
#endif
	return true;
}

/**
 * It removes a rule only if it exists.
 *
 * @info
 */
static void
remove_rule(struct ipt_pknock_info *info)
{
	struct ipt_pknock_rule *rule = NULL;
	struct list_head *pos = NULL, *n = NULL;
	struct peer *peer = NULL;
	int i;
#if DEBUG
	int found = 0;
#endif
	int hash = pknock_hash(info->rule_name, info->rule_name_len,
                                ipt_pknock_hash_rnd, rule_hashsize);

	if (list_empty(&rule_hashtable[hash])) return;

	list_for_each_safe(pos, n, &rule_hashtable[hash]) {
		rule = list_entry(pos, struct ipt_pknock_rule, head);

		if (rulecmp(info, rule) == 0) {
#if DEBUG
			found = 1;
#endif
			rule->ref_count--;
			break;
		}
	}
#if DEBUG
	if (!found) {
		printk(KERN_INFO MOD "(N) rule not found: %s.\n",
                        info->rule_name);
		return;
	}
#endif
	if (rule && rule->ref_count == 0) {
		hashtable_for_each_safe(pos, n, rule->peer_head,
                        peer_hashsize, i) {

                        peer = list_entry(pos, struct peer, head);
			if (peer != NULL) {
				DEBUGP("DELETED", peer);
				list_del(pos);
				kfree(peer);
			}
		}
		if (rule->status_proc)
                        remove_proc_entry(info->rule_name, pde);
#if DEBUG
		printk(KERN_INFO MOD "(D) rule deleted: %s.\n",
                        rule->rule_name);
#endif
		if (timer_pending(&rule->timer))
			del_timer(&rule->timer);

		list_del(&rule->head);
		kfree(rule->peer_head);
		kfree(rule);
	}
}

/**
 * If peer status exist in the list it returns peer status, if not it returns NULL.
 *
 * @rule
 * @ip
 * @return: peer or NULL
 */
static inline struct peer *
get_peer(struct ipt_pknock_rule *rule, u_int32_t ip)
{
	struct peer *peer = NULL;
	struct list_head *pos = NULL, *n = NULL;
	int hash;

	ip = ntohl(ip);

	hash = pknock_hash(&ip, sizeof(ip), ipt_pknock_hash_rnd, peer_hashsize);

	list_for_each_safe(pos, n, &rule->peer_head[hash]) {
		peer = list_entry(pos, struct peer, head);
		if (peer->ip == ip) return peer;
	}
	return NULL;
}

/**
 * Reset the knock sequence status of the peer.
 *
 * @peer
 */
static inline void
reset_knock_status(struct peer *peer)
{
	peer->id_port_knocked	= 1;
	peer->status		= ST_INIT;
}

/**
 * It creates a new peer matching status.
 *
 * @rule
 * @ip
 * @proto
 * @return: peer or NULL
 */
static inline struct peer *
new_peer(u_int32_t ip, u_int8_t proto)
{
	struct peer *peer = NULL;

	if ((peer = kmalloc(sizeof (*peer), GFP_ATOMIC)) == NULL) {
		printk(KERN_ERR MOD "kmalloc() error in new_peer().\n");
		return NULL;
	}

	INIT_LIST_HEAD(&peer->head);
	peer->ip	= ntohl(ip);
	peer->proto	= proto;
	peer->timestamp = jiffies/HZ;
	peer->login_min = 0;
	reset_knock_status(peer);

	return peer;
}

/**
 * It adds a new peer matching status to the list.
 *
 * @peer
 * @rule
 */
static inline void
add_peer(struct peer *peer, struct ipt_pknock_rule *rule)
{
	int hash = pknock_hash(&peer->ip, sizeof(peer->ip),
                                ipt_pknock_hash_rnd, peer_hashsize);
	list_add(&peer->head, &rule->peer_head[hash]);
}

/**
 * It removes a peer matching status.
 *
 * @peer
 */
static inline void
remove_peer(struct peer *peer)
{
	list_del(&peer->head);
	if (peer) kfree(peer);
}

/**
 * @peer
 * @info
 * @port
 * @return: 1 success, 0 failure
 */
static inline bool
is_first_knock(const struct peer *peer, const struct ipt_pknock_info *info,
                u_int16_t port)
{
	return (peer == NULL && info->port[0] == port) ? 1 : 0;
}

/**
 * @peer
 * @info
 * @port
 * @return: 1 success, 0 failure
 */
static inline bool
is_wrong_knock(const struct peer *peer, const struct ipt_pknock_info *info,
		u_int16_t port)
{
	return peer && (info->port[peer->id_port_knocked-1] != port);
}

/**
 * @peer
 * @info
 * @return: 1 success, 0 failure
 */
static inline bool
is_last_knock(const struct peer *peer, const struct ipt_pknock_info *info)
{
	return peer && (peer->id_port_knocked-1 == info->count_ports);
}

/**
 * @peer
 * @return: 1 success, 0 failure
 */
static inline bool
is_allowed(const struct peer *peer)
{
	return peer && (peer->status == ST_ALLOWED);
}

/**
 * Sends a message to user space through netlink sockets.
 *
 * @info
 * @peer
 * @return: 1 success, 0 otherwise
 */
static bool
msg_to_userspace_nl(const struct ipt_pknock_info *info,
                const struct peer *peer, int multicast_group)
{
	struct cn_msg *m;
	struct ipt_pknock_nl_msg msg;

	m = kmalloc(sizeof(*m) + sizeof(msg), GFP_ATOMIC);
	if (!m) {
		printk(KERN_ERR MOD "kmalloc() error in "
                        "msg_to_userspace_nl().\n");
		return false;
	}

	memset(m, 0, sizeof(*m) + sizeof(msg));
	m->seq = 0;
	m->len = sizeof(msg);

	msg.peer_ip = peer->ip;
	scnprintf(msg.rule_name, info->rule_name_len + 1, info->rule_name);

	memcpy(m + 1, (char *)&msg, m->len);

	cn_netlink_send(m, multicast_group, GFP_ATOMIC);

	kfree(m);

	return true;
}

/**
 * Transforms a sequence of characters to hexadecimal.
 *
 * @out: the hexadecimal result
 * @crypt: the original sequence
 * @size
 */
static void
crypt_to_hex(char *out, char *crypt, int size)
{
	int i;
	for (i=0; i < size; i++) {
		unsigned char c = crypt[i];
		*out++ = '0' + ((c&0xf0)>>4) + (c>=0xa0)*('a'-'9'-1);
		*out++ = '0' + (c&0x0f) + ((c&0x0f)>=0x0a)*('a'-'9'-1);
	}
}

/**
 * Checks that the payload has the hmac(secret+ipsrc+epoch_min).
 *
 * @secret
 * @secret_len
 * @ipsrc
 * @payload
 * @payload_len
 * @return: 1 success, 0 failure
 */
static int
has_secret(unsigned char *secret, int secret_len, u_int32_t ipsrc,
        unsigned char *payload, int payload_len)
{
	struct scatterlist sg[2];
	char result[64]; // 64 bytes * 8 = 512 bits
	char *hexresult = NULL;
	int hexa_size;
	int ret = 0;
	int epoch_min;

	if (payload_len == 0)
		return 0;

	/*
	 * hexa:  4bits
	 * ascii: 8bits
	 * hexa = ascii * 2
	 */
	hexa_size = crypto.size * 2;

	/* + 1 cause we MUST add NULL in the payload */
	if (payload_len != hexa_size + 1)
		return 0;

	hexresult = kmalloc(sizeof(char) * hexa_size, GFP_ATOMIC);
	if (hexresult == NULL) {
		printk(KERN_ERR MOD "kmalloc() error in has_secret().\n");
		return 0;
	}

	memset(result, 0, 64);
	memset(hexresult, 0, (sizeof(char) * hexa_size));

	epoch_min = get_epoch_minute();

	sg_set_buf(&sg[0], &ipsrc, sizeof(ipsrc));
	sg_set_buf(&sg[1], &epoch_min, sizeof(epoch_min));

	ret = crypto_hash_setkey(crypto.tfm, secret, secret_len);
	if (ret) {
		printk("crypto_hash_setkey() failed ret=%d\n", ret);
		return ret;
	}

	/*
	 * The third parameter is the number of bytes INSIDE the sg!
	 * 4 bytes IP (32 bits) +
	 * 4 bytes int epoch_min (32 bits)
	 */
	ret = crypto_hash_digest(&crypto.desc, sg, 8, result);
	if (ret) {
		printk("crypto_hash_digest() failed ret=%d\n", ret);
		return ret;
	}

	crypt_to_hex(hexresult, result, crypto.size);

	if (memcmp(hexresult, payload, hexa_size) != 0) {
#if DEBUG
		printk(KERN_INFO MOD "secret match failed\n");
#endif
		goto out;
	}

	ret = 1;

out:
	if (hexresult != NULL) kfree(hexresult);
	return ret;
}

/**
 * If the peer pass the security policy
 *
 * @peer
 * @info
 * @payload
 * @payload_len
 * @return: 1 if pass security, 0 otherwise
 */
static bool
pass_security(struct peer *peer, const struct ipt_pknock_info *info,
        unsigned char *payload, int payload_len)
{
	if (is_allowed(peer))
		return true;

	/* The peer can't log more than once during the same minute. */
	if (has_logged_during_this_minute(peer)) {
		DEBUGP("BLOCKED", peer);
		return false;
	}
	/* Check for OPEN secret */
	if (!has_secret((unsigned char *)info->open_secret,
                (int)info->open_secret_len, htonl(peer->ip),
		payload, payload_len))
	{
		return false;
        }
	return true;
}

/**
 * It updates the peer matching status.
 *
 * @peer
 * @info
 * @rule
 * @hdr
 * @return: 1 if allowed, 0 otherwise
 */
static bool
update_peer(struct peer *peer, const struct ipt_pknock_info *info,
		struct ipt_pknock_rule *rule,
		const struct transport_data *hdr)
{
	unsigned long time;

	if (is_wrong_knock(peer, info, hdr->port)) {
		DEBUGP("DIDN'T MATCH", peer);
		/* Peer must start the sequence from scratch. */
		if (info->option & IPT_PKNOCK_STRICT)
			reset_knock_status(peer);

		return false;
	}

	/* If security is needed. */
	if (info->option & IPT_PKNOCK_OPENSECRET ) {
		if (hdr->proto != IPPROTO_UDP)
			return false;

		if (!pass_security(peer, info, hdr->payload,
                        hdr->payload_len)) 
		{
                        return false;
		}
	}

	/* Just update the timer when there is a state change. */
	update_rule_timer(rule);

	peer->id_port_knocked++;

	if (is_last_knock(peer, info)) {
		peer->status = ST_ALLOWED;

		DEBUGP("ALLOWED", peer);

		if (nl_multicast_group > 0)
			msg_to_userspace_nl(info, peer, nl_multicast_group);

		peer->login_min = get_epoch_minute();
		return true;
	}

	/* Controls the max matching time between ports. */
	if (info->option & IPT_PKNOCK_TIME) {
		time = jiffies/HZ;

		if (is_time_exceeded(peer, info->max_time)) {
#if DEBUG
			DEBUGP("TIME EXCEEDED", peer);
			DEBUGP("DESTROYED", peer);
			printk(KERN_INFO MOD "max_time: %ld - time: %ld\n",
					peer->timestamp + info->max_time,
					time);
#endif
			remove_peer(peer);
			return false;
		}
		peer->timestamp = time;
	}
	DEBUGP("MATCHING", peer);
	peer->status = ST_MATCHING;
	return false;
}

/**
 * Make the peer no more ALLOWED sending a payload with a special secret for
 * closure.
 *
 * @peer
 * @info
 * @payload
 * @payload_len
 * @return: 1 if close knock, 0 otherwise
 */
static inline bool
is_close_knock(const struct peer *peer, const struct ipt_pknock_info *info,
		unsigned char *payload, int payload_len)
{
	/* Check for CLOSE secret. */
	if (has_secret((unsigned char *)info->close_secret,
				(int)info->close_secret_len, htonl(peer->ip),
				payload, payload_len))
	{
		DEBUGP("RESET", peer);
		return true;
	}
	return false;
}

#if LINUX_VERSION_CODE >= KERNEL_VERSION(2,6,23)
static bool
#else
static int
#endif
match(const struct sk_buff *skb,
	const struct net_device *in,
	const struct net_device *out,
#if LINUX_VERSION_CODE >= KERNEL_VERSION(2,6,17)
        const struct xt_match *match,
#endif
	const void *matchinfo,
	int offset,
#if LINUX_VERSION_CODE >= KERNEL_VERSION(2,6,16)
        unsigned int protoff,
#endif
	bool *hotdrop)
{
	const struct ipt_pknock_info *info = matchinfo;
	struct ipt_pknock_rule *rule = NULL;
	struct peer *peer = NULL;
#if LINUX_VERSION_CODE >= KERNEL_VERSION(2,6,22)
	struct iphdr *iph = ip_hdr(skb);
#else
	struct iphdr *iph = skb->nh.iph;
#endif
	int hdr_len = 0;
	__be16 _ports[2], *pptr = NULL;
	struct transport_data hdr = {0, 0, 0, NULL};
#if LINUX_VERSION_CODE >= KERNEL_VERSION(2,6,23)
	bool ret = false;
#else
	int ret = 0;
#endif

	pptr = skb_header_pointer(skb, protoff, sizeof _ports, &_ports);

	if (pptr == NULL) {
		/* We've been asked to examine this packet, and we
		 * can't. Hence, no choice but to drop.
		 */
		duprintf("Dropping evil offset=0 tinygram.\n");
#if LINUX_VERSION_CODE >= KERNEL_VERSION(2,6,23)
		*hotdrop = true;
		return false;
#else
		*hotdrop = 1;
		return 0;
#endif
	}

	hdr.port = ntohs(pptr[1]);

	switch ((hdr.proto = iph->protocol)) {
		case IPPROTO_TCP:
			break;

		case IPPROTO_UDP:
			hdr_len = (iph->ihl * 4) + sizeof(struct udphdr);
			break;

		default:
			printk(KERN_INFO MOD "IP payload protocol "
					"is neither tcp nor udp.\n");
			return false;
	}

	spin_lock_bh(&list_lock);

	/* Searches a rule from the list depending on info structure options. */
	if ((rule = search_rule(info)) == NULL) {
		printk(KERN_INFO MOD "The rule %s doesn't exist.\n",
				info->rule_name);
		goto out;
	}

	/* Gives the peer matching status added to rule depending on ip src. */
	peer = get_peer(rule, iph->saddr);

	if (info->option & IPT_PKNOCK_CHECKIP) {
		ret = is_allowed(peer);
		goto out;
	}
	
	if (iph->protocol == IPPROTO_UDP) {
		hdr.payload = (void *)iph + hdr_len;
		hdr.payload_len = skb->len - hdr_len;
	}
	
	/* Sets, updates, removes or checks the peer matching status. */
	if (info->option & IPT_PKNOCK_KNOCKPORT) {
		if ((ret = is_allowed(peer))) {
			if (info->option & IPT_PKNOCK_CLOSESECRET
                                && iph->protocol == IPPROTO_UDP)
			{
                                if (is_close_knock(peer, info, hdr.payload,
                                        hdr.payload_len)) 
				{
                                        reset_knock_status(peer);
#if LINUX_VERSION_CODE >= KERNEL_VERSION(2,6,23)
					ret = false;
#else
					ret = 0;
#endif
				}
			}
			goto out;
		}

		if (is_first_knock(peer, info, hdr.port)) {
			peer = new_peer(iph->saddr, iph->protocol);
			add_peer(peer, rule);
		}

		if (peer == NULL) goto out;

		update_peer(peer, info, rule, &hdr);
	}

out:
#if DEBUG
	if (ret)
		DEBUGP("PASS OK", peer);
#endif
	spin_unlock_bh(&list_lock);
	return ret;
}

#if LINUX_VERSION_CODE >= KERNEL_VERSION(2,6,23)
#define RETURN_ERR(err) do { printk(KERN_ERR MOD err); return false; } while (0)
#else
#define RETURN_ERR(err) do { printk(KERN_ERR MOD err); return 0; } while (0)
#endif

#if LINUX_VERSION_CODE >= KERNEL_VERSION(2,6,23)
static bool
#else
static int
#endif
checkentry(const char *tablename,
#if LINUX_VERSION_CODE >= KERNEL_VERSION(2,6,16)
	const void *ip,
#else
	const struct ipt_ip *ip,
#endif
#if LINUX_VERSION_CODE >= KERNEL_VERSION(2,6,17)	
        const struct xt_match *match,
#endif
	void *matchinfo,
#if LINUX_VERSION_CODE < KERNEL_VERSION(2,6,17)
	unsigned int matchsize,
#endif
	unsigned int hook_mask)
{
	struct ipt_pknock_info *info = matchinfo;

	/* Singleton. */
	if (!rule_hashtable) {
		if (!(rule_hashtable = alloc_hashtable(rule_hashsize)))
			RETURN_ERR("alloc_hashtable() error in checkentry()\n");

		get_random_bytes(&ipt_pknock_hash_rnd,
                                sizeof (ipt_pknock_hash_rnd));
	}

	if (!add_rule(info))
		RETURN_ERR("add_rule() error in checkentry() function.\n");

	if (!(info->option & IPT_PKNOCK_NAME))
		RETURN_ERR("You must specify --name option.\n");

	if ((info->option & IPT_PKNOCK_OPENSECRET) && (info->count_ports != 1))
		RETURN_ERR("--opensecret must have just one knock port\n");

	if (info->option & IPT_PKNOCK_KNOCKPORT) {
		if (info->option & IPT_PKNOCK_CHECKIP) {
			RETURN_ERR("Can't specify --knockports with "
					"--checkip.\n");
		}
		if ((info->option & IPT_PKNOCK_OPENSECRET) &&
				!(info->option & IPT_PKNOCK_CLOSESECRET)) 
		{
			RETURN_ERR("--opensecret must go with "
					"--closesecret.\n");
		}
		if ((info->option & IPT_PKNOCK_CLOSESECRET) &&
				!(info->option & IPT_PKNOCK_OPENSECRET)) 
		{
			RETURN_ERR("--closesecret must go with "
					"--opensecret.\n");
		}
	}

	if (info->option & IPT_PKNOCK_CHECKIP) {
		if (info->option & IPT_PKNOCK_KNOCKPORT)
		{
			RETURN_ERR("Can't specify --checkip with "
					"--knockports.\n");
		}
		if ((info->option & IPT_PKNOCK_OPENSECRET) ||
				(info->option & IPT_PKNOCK_CLOSESECRET))
		{
			RETURN_ERR("Can't specify --opensecret and "
					"--closesecret with --checkip.\n");
		}
		if (info->option & IPT_PKNOCK_TIME)
			RETURN_ERR("Can't specify --time with --checkip.\n");
	}

	if (info->option & IPT_PKNOCK_OPENSECRET) {
		if (info->open_secret_len == info->close_secret_len) {
			if (memcmp(info->open_secret, info->close_secret,
						info->open_secret_len) == 0)
			{
				RETURN_ERR("opensecret & closesecret cannot "
						"be equal.\n");
			}
		}
	}

#if LINUX_VERSION_CODE >= KERNEL_VERSION(2,6,23)
	return true;
#else
	return 1;
#endif
}

static void
destroy(
#if LINUX_VERSION_CODE >= KERNEL_VERSION(2,6,17)
		const struct xt_match *match, void *matchinfo)
#else
		void *matchinfo, unsigned int matchsize)
#endif
{
	struct ipt_pknock_info *info = matchinfo;
	/* Removes a rule only if it exits and ref_count is equal to 0. */
	remove_rule(info);
}

static struct xt_match ipt_pknock_match __read_mostly = {
	.name		= "pknock",
#if LINUX_VERSION_CODE >= KERNEL_VERSION(2,6,21)	
	.family		= AF_INET,
#endif
#if LINUX_VERSION_CODE >= KERNEL_VERSION(2,6,17)	
        .matchsize      = sizeof (struct ipt_pknock_info),
#endif
	.match		= match,
	.checkentry	= checkentry,
	.destroy	= destroy,
	.me		= THIS_MODULE
};

static int __init ipt_pknock_init(void)
{
	printk(KERN_INFO MOD "register.\n");

	if (request_module(crypto.algo) < 0) {
		printk(KERN_ERR MOD "request_module('%s') error.\n",
                        crypto.algo);
		return -1;
	}

	crypto.tfm = crypto_alloc_hash(crypto.algo, 0, CRYPTO_ALG_ASYNC);

	if (crypto.tfm == NULL) {
		printk(KERN_ERR MOD "failed to load transform for %s\n",
                        crypto.algo);
		return -1;
	}

	crypto.size = crypto_hash_digestsize(crypto.tfm);
	crypto.desc.tfm = crypto.tfm;
	crypto.desc.flags = 0;

	if (!(pde = proc_mkdir("ipt_pknock", proc_net))) {
		printk(KERN_ERR MOD "proc_mkdir() error in _init().\n");
		return -1;
	}
#if LINUX_VERSION_CODE >= KERNEL_VERSION(2,6,21)
	return xt_register_match(&ipt_pknock_match);
#else
	return ipt_register_match(&ipt_pknock_match);
#endif
}

static void __exit ipt_pknock_fini(void)
{
	printk(KERN_INFO MOD "unregister.\n");
	remove_proc_entry("ipt_pknock", proc_net);
#if LINUX_VERSION_CODE >= KERNEL_VERSION(2,6,21)
	xt_unregister_match(&ipt_pknock_match);
#else
	ipt_unregister_match(&ipt_pknock_match);
#endif
	kfree(rule_hashtable);

	if (crypto.tfm != NULL) crypto_free_hash(crypto.tfm);
}

module_init(ipt_pknock_init);
module_exit(ipt_pknock_fini);
