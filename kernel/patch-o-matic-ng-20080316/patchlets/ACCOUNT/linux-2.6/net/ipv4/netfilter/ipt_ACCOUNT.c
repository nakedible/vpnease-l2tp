/***************************************************************************
 *   This is a module which is used for counting packets.                  *
 *   See http://www.intra2net.com/opensource/ipt_account                   *
 *   for further information                                               *
 *                                                                         * 
 *   Copyright (C) 2004-2007 by Intra2net AG                               *
 *   opensource@intra2net.com                                              *
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License                  *
 *   version 2 as published by the Free Software Foundation;               *
 *                                                                         *
 ***************************************************************************/

#include <linux/module.h>
#include <linux/version.h>
#include <linux/skbuff.h>
#include <linux/ip.h>
#include <net/icmp.h>
#include <net/udp.h>
#include <net/tcp.h>
#include <linux/netfilter_ipv4/ip_tables.h>
#include <asm/semaphore.h>
#include <linux/kernel.h>
#include <linux/mm.h>
#include <linux/string.h>
#include <linux/spinlock.h>
#include <asm/uaccess.h>

#include <net/route.h>
#include <linux/netfilter_ipv4/ipt_ACCOUNT.h>

#if 0
#define DEBUGP printk
#else
#define DEBUGP(format, args...)
#endif

#if (PAGE_SIZE < 4096)
#error "ipt_ACCOUNT needs at least a PAGE_SIZE of 4096"
#endif

static struct ipt_acc_table *ipt_acc_tables = NULL;
static struct ipt_acc_handle *ipt_acc_handles = NULL;
static void *ipt_acc_tmpbuf = NULL;

/* Spinlock used for manipulating the current accounting tables/data */
static DEFINE_SPINLOCK(ipt_acc_lock);
/* Mutex (semaphore) used for manipulating userspace handles/snapshot data */
static struct semaphore ipt_acc_userspace_mutex;

/* Allocates a page and clears it */
static void *ipt_acc_zalloc_page(void)
{
    // Don't use get_zeroed_page until it's fixed in the kernel.
    // get_zeroed_page(GFP_ATOMIC)
    void *mem = (void *)__get_free_page(GFP_ATOMIC);
    if (mem) {
        memset (mem, 0, PAGE_SIZE);
    }

    return mem;
}

/* Recursive free of all data structures */
static void ipt_acc_data_free(void *data, unsigned char depth)
{
    /* Empty data set */
    if (!data)
        return;

    /* Free for 8 bit network */
    if (depth == 0) {
        free_page((unsigned long)data);
        return;
    }

    /* Free for 16 bit network */
    if (depth == 1) {
        struct ipt_acc_mask_16 *mask_16 = (struct ipt_acc_mask_16 *)data;
        unsigned int b;
        for (b=0; b <= 255; b++) {
            if (mask_16->mask_24[b]) {
                free_page((unsigned long)mask_16->mask_24[b]);
            }
        }
        free_page((unsigned long)data);
        return;
    }

    /* Free for 24 bit network */
    if (depth == 2) {
        unsigned int a, b;
        for (a=0; a <= 255; a++) {
            if (((struct ipt_acc_mask_8 *)data)->mask_16[a]) {
                struct ipt_acc_mask_16 *mask_16 = (struct ipt_acc_mask_16*)
                                   ((struct ipt_acc_mask_8 *)data)->mask_16[a];

                for (b=0; b <= 255; b++) {
                    if (mask_16->mask_24[b]) {
                        free_page((unsigned long)mask_16->mask_24[b]);
                    }
                }
                free_page((unsigned long)mask_16);
            }
        }
        free_page((unsigned long)data);
        return;
    }

    printk("ACCOUNT: ipt_acc_data_free called with unknown depth: %d\n", 
           depth);
    return;
}

/* Look for existing table / insert new one. 
   Return internal ID or -1 on error */
static int ipt_acc_table_insert(char *name, u_int32_t ip, u_int32_t netmask)
{
    unsigned int i;

    DEBUGP("ACCOUNT: ipt_acc_table_insert: %s, %u.%u.%u.%u/%u.%u.%u.%u\n",
                                         name, NIPQUAD(ip), NIPQUAD(netmask));

    /* Look for existing table */
    for (i = 0; i < ACCOUNT_MAX_TABLES; i++) {
        if (strncmp(ipt_acc_tables[i].name, name, 
                    ACCOUNT_TABLE_NAME_LEN) == 0) {
            DEBUGP("ACCOUNT: Found existing slot: %d - "
                   "%u.%u.%u.%u/%u.%u.%u.%u\n", i, 
                   NIPQUAD(ipt_acc_tables[i].ip), 
                   NIPQUAD(ipt_acc_tables[i].netmask));

            if (ipt_acc_tables[i].ip != ip 
                || ipt_acc_tables[i].netmask != netmask) {
                printk("ACCOUNT: Table %s found, but IP/netmask mismatch. "
                       "IP/netmask found: %u.%u.%u.%u/%u.%u.%u.%u\n",
                       name, NIPQUAD(ipt_acc_tables[i].ip), 
                       NIPQUAD(ipt_acc_tables[i].netmask));
                return -1;
            }

            ipt_acc_tables[i].refcount++;
            DEBUGP("ACCOUNT: Refcount: %d\n", ipt_acc_tables[i].refcount);
            return i;
        }
    }

    /* Insert new table */
    for (i = 0; i < ACCOUNT_MAX_TABLES; i++) {
        /* Found free slot */
        if (ipt_acc_tables[i].name[0] == 0) {
            unsigned int netsize=0;
            u_int32_t calc_mask;
            int j;  /* needs to be signed, otherwise we risk endless loop */

            DEBUGP("ACCOUNT: Found free slot: %d\n", i);
            strncpy (ipt_acc_tables[i].name, name, ACCOUNT_TABLE_NAME_LEN-1);

            ipt_acc_tables[i].ip = ip;
            ipt_acc_tables[i].netmask = netmask;

            /* Calculate netsize */
            calc_mask = htonl(netmask);
            for (j = 31; j >= 0; j--) {
                if (calc_mask&(1<<j))
                    netsize++;
                else
                    break;
            }

            /* Calculate depth from netsize */
            if (netsize >= 24)
                ipt_acc_tables[i].depth = 0;
            else if (netsize >= 16)
                ipt_acc_tables[i].depth = 1;
            else if(netsize >= 8)
                ipt_acc_tables[i].depth = 2;

            DEBUGP("ACCOUNT: calculated netsize: %u -> "
                   "ipt_acc_table depth %u\n", netsize, 
                   ipt_acc_tables[i].depth);

            ipt_acc_tables[i].refcount++;
            if ((ipt_acc_tables[i].data
                = ipt_acc_zalloc_page()) == NULL) {
                printk("ACCOUNT: out of memory for data of table: %s\n", name);
                memset(&ipt_acc_tables[i], 0, 
                       sizeof(struct ipt_acc_table));
                return -1;
            }

            return i;
        }
    }

    /* No free slot found */
    printk("ACCOUNT: No free table slot found (max: %d). "
           "Please increase ACCOUNT_MAX_TABLES.\n", ACCOUNT_MAX_TABLES);
    return -1;
}

#if LINUX_VERSION_CODE >= KERNEL_VERSION(2,6,23)
static bool ipt_acc_checkentry(const char *tablename,
#else
static int ipt_acc_checkentry(const char *tablename,
#endif
#if LINUX_VERSION_CODE >= KERNEL_VERSION(2,6,16)
                              const void *e,
#else
                              const struct ipt_entry *e,
#endif
#if LINUX_VERSION_CODE >= KERNEL_VERSION(2,6,17)
                              const struct xt_target *target,
#endif
                              void *targinfo,
#if LINUX_VERSION_CODE < KERNEL_VERSION(2,6,19)
                              unsigned int targinfosize,
#endif
                              unsigned int hook_mask)
{
    struct ipt_acc_info *info = targinfo;
    int table_nr;

#if LINUX_VERSION_CODE < KERNEL_VERSION(2,6,17)
    if (targinfosize != IPT_ALIGN(sizeof(struct ipt_acc_info))) {
        DEBUGP("ACCOUNT: targinfosize %u != %u\n",
               targinfosize, IPT_ALIGN(sizeof(struct ipt_acc_info)));
        return 0;
    }
#endif

    spin_lock_bh(&ipt_acc_lock);
    table_nr = ipt_acc_table_insert(info->table_name, info->net_ip,
                                                      info->net_mask);
    spin_unlock_bh(&ipt_acc_lock);

    if (table_nr == -1) {
        printk("ACCOUNT: Table insert problem. Aborting\n");
#if LINUX_VERSION_CODE >= KERNEL_VERSION(2,6,23)
        return false;
#else
        return 0;
#endif
    }
    /* Table nr caching so we don't have to do an extra string compare 
       for every packet */
    info->table_nr = table_nr;

#if LINUX_VERSION_CODE >= KERNEL_VERSION(2,6,23)
    return true;
#else
    return 1;
#endif
}

static void ipt_acc_destroy(
#if LINUX_VERSION_CODE >= KERNEL_VERSION(2,6,17)
                            const struct xt_target *target,
#endif
#if LINUX_VERSION_CODE >= KERNEL_VERSION(2,6,19)
                            void *targinfo)
#else
                            void *targinfo,
                            unsigned int targinfosize)
#endif
{
    unsigned int i;
    struct ipt_acc_info *info = targinfo;

#if LINUX_VERSION_CODE < KERNEL_VERSION(2,6,17)
    if (targinfosize != IPT_ALIGN(sizeof(struct ipt_acc_info))) {
        DEBUGP("ACCOUNT: targinfosize %u != %u\n",
               targinfosize, IPT_ALIGN(sizeof(struct ipt_acc_info)));
    }
#endif

    spin_lock_bh(&ipt_acc_lock);

    DEBUGP("ACCOUNT: ipt_acc_deleteentry called for table: %s (#%d)\n", 
           info->table_name, info->table_nr);

    info->table_nr = -1;    /* Set back to original state */

    /* Look for table */
    for (i = 0; i < ACCOUNT_MAX_TABLES; i++) {
        if (strncmp(ipt_acc_tables[i].name, info->table_name, 
                    ACCOUNT_TABLE_NAME_LEN) == 0) {
            DEBUGP("ACCOUNT: Found table at slot: %d\n", i);

            ipt_acc_tables[i].refcount--;
            DEBUGP("ACCOUNT: Refcount left: %d\n", 
                   ipt_acc_tables[i].refcount);

            /* Table not needed anymore? */
            if (ipt_acc_tables[i].refcount == 0) {
                DEBUGP("ACCOUNT: Destroying table at slot: %d\n", i);
                ipt_acc_data_free(ipt_acc_tables[i].data, 
                                      ipt_acc_tables[i].depth);
                memset(&ipt_acc_tables[i], 0, 
                       sizeof(struct ipt_acc_table));
            }

            spin_unlock_bh(&ipt_acc_lock);
            return;
        }
    }

    /* Table not found */
    printk("ACCOUNT: Table %s not found for destroy\n", info->table_name);
    spin_unlock_bh(&ipt_acc_lock);
}

static void ipt_acc_depth0_insert(struct ipt_acc_mask_24 *mask_24,
                               u_int32_t net_ip, u_int32_t netmask,
                               u_int32_t src_ip, u_int32_t dst_ip,
                               u_int32_t size, u_int32_t *itemcount)
{
    unsigned char is_src = 0, is_dst = 0, src_slot, dst_slot;
    char is_src_new_ip = 0, is_dst_new_ip = 0; /* Check if this entry is new */

    DEBUGP("ACCOUNT: ipt_acc_depth0_insert: %u.%u.%u.%u/%u.%u.%u.%u "
           "for net %u.%u.%u.%u/%u.%u.%u.%u, size: %u\n", NIPQUAD(src_ip), 
           NIPQUAD(dst_ip), NIPQUAD(net_ip), NIPQUAD(netmask), size);

    /* Check if src/dst is inside our network. */
    /* Special: net_ip = 0.0.0.0/0 gets stored as src in slot 0 */
    if (!netmask)
        src_ip = 0;
    if ((net_ip&netmask) == (src_ip&netmask))
        is_src = 1;
    if ((net_ip&netmask) == (dst_ip&netmask) && netmask)
        is_dst = 1;

    if (!is_src && !is_dst) {
        DEBUGP("ACCOUNT: Skipping packet %u.%u.%u.%u/%u.%u.%u.%u "
               "for net %u.%u.%u.%u/%u.%u.%u.%u\n", NIPQUAD(src_ip), 
               NIPQUAD(dst_ip), NIPQUAD(net_ip), NIPQUAD(netmask));
        return;
    }

    /* Calculate array positions */
    src_slot = (unsigned char)((src_ip&0xFF000000) >> 24);
    dst_slot = (unsigned char)((dst_ip&0xFF000000) >> 24);

    /* Increase size counters */
    if (is_src) {
        /* Calculate network slot */
        DEBUGP("ACCOUNT: Calculated SRC 8 bit network slot: %d\n", src_slot);
        if (!mask_24->ip[src_slot].src_packets 
            && !mask_24->ip[src_slot].dst_packets)
            is_src_new_ip = 1;

        mask_24->ip[src_slot].src_packets++;
        mask_24->ip[src_slot].src_bytes+=size;
    }
    if (is_dst) {
        DEBUGP("ACCOUNT: Calculated DST 8 bit network slot: %d\n", dst_slot);
        if (!mask_24->ip[dst_slot].src_packets 
            && !mask_24->ip[dst_slot].dst_packets)
            is_dst_new_ip = 1;

        mask_24->ip[dst_slot].dst_packets++;
        mask_24->ip[dst_slot].dst_bytes+=size;
    }

    /* Increase itemcounter */
    DEBUGP("ACCOUNT: Itemcounter before: %d\n", *itemcount);
    if (src_slot == dst_slot) {
        if (is_src_new_ip || is_dst_new_ip) {
            DEBUGP("ACCOUNT: src_slot == dst_slot: %d, %d\n", 
                   is_src_new_ip, is_dst_new_ip);
            (*itemcount)++;
        }
    } else {
        if (is_src_new_ip) {
            DEBUGP("ACCOUNT: New src_ip: %u.%u.%u.%u\n", NIPQUAD(src_ip));
            (*itemcount)++;
        }
        if (is_dst_new_ip) {
            DEBUGP("ACCOUNT: New dst_ip: %u.%u.%u.%u\n", NIPQUAD(dst_ip));
            (*itemcount)++;
        }
    }
    DEBUGP("ACCOUNT: Itemcounter after: %d\n", *itemcount);
}

static void ipt_acc_depth1_insert(struct ipt_acc_mask_16 *mask_16, 
                               u_int32_t net_ip, u_int32_t netmask, 
                               u_int32_t src_ip, u_int32_t dst_ip,
                               u_int32_t size, u_int32_t *itemcount)
{
    /* Do we need to process src IP? */
    if ((net_ip&netmask) == (src_ip&netmask)) {
        unsigned char slot = (unsigned char)((src_ip&0x00FF0000) >> 16);
        DEBUGP("ACCOUNT: Calculated SRC 16 bit network slot: %d\n", slot);

        /* Do we need to create a new mask_24 bucket? */
        if (!mask_16->mask_24[slot] && (mask_16->mask_24[slot] = 
             ipt_acc_zalloc_page()) == NULL) {
            printk("ACCOUNT: Can't process packet because out of memory!\n");
            return;
        }

        ipt_acc_depth0_insert((struct ipt_acc_mask_24 *)mask_16->mask_24[slot],
                                  net_ip, netmask, src_ip, 0, size, itemcount);
    }

    /* Do we need to process dst IP? */
    if ((net_ip&netmask) == (dst_ip&netmask)) {
        unsigned char slot = (unsigned char)((dst_ip&0x00FF0000) >> 16);
        DEBUGP("ACCOUNT: Calculated DST 16 bit network slot: %d\n", slot);

        /* Do we need to create a new mask_24 bucket? */
        if (!mask_16->mask_24[slot] && (mask_16->mask_24[slot] 
            = ipt_acc_zalloc_page()) == NULL) {
            printk("ACCOUT: Can't process packet because out of memory!\n");
            return;
        }

        ipt_acc_depth0_insert((struct ipt_acc_mask_24 *)mask_16->mask_24[slot],
                                  net_ip, netmask, 0, dst_ip, size, itemcount);
    }
}

static void ipt_acc_depth2_insert(struct ipt_acc_mask_8 *mask_8, 
                               u_int32_t net_ip, u_int32_t netmask,
                               u_int32_t src_ip, u_int32_t dst_ip,
                               u_int32_t size, u_int32_t *itemcount)
{
    /* Do we need to process src IP? */
    if ((net_ip&netmask) == (src_ip&netmask)) {
        unsigned char slot = (unsigned char)((src_ip&0x0000FF00) >> 8);
        DEBUGP("ACCOUNT: Calculated SRC 24 bit network slot: %d\n", slot);

        /* Do we need to create a new mask_24 bucket? */
        if (!mask_8->mask_16[slot] && (mask_8->mask_16[slot] 
            = ipt_acc_zalloc_page()) == NULL) {
            printk("ACCOUNT: Can't process packet because out of memory!\n");
            return;
        }

        ipt_acc_depth1_insert((struct ipt_acc_mask_16 *)mask_8->mask_16[slot],
                                  net_ip, netmask, src_ip, 0, size, itemcount);
    }

    /* Do we need to process dst IP? */
    if ((net_ip&netmask) == (dst_ip&netmask)) {
        unsigned char slot = (unsigned char)((dst_ip&0x0000FF00) >> 8);
        DEBUGP("ACCOUNT: Calculated DST 24 bit network slot: %d\n", slot);

        /* Do we need to create a new mask_24 bucket? */
        if (!mask_8->mask_16[slot] && (mask_8->mask_16[slot] 
            = ipt_acc_zalloc_page()) == NULL) {
            printk("ACCOUNT: Can't process packet because out of memory!\n");
            return;
        }

        ipt_acc_depth1_insert((struct ipt_acc_mask_16 *)mask_8->mask_16[slot],
                                  net_ip, netmask, 0, dst_ip, size, itemcount);
    }
}

#if LINUX_VERSION_CODE >= KERNEL_VERSION(2,6,24)
static unsigned int ipt_acc_target(struct sk_buff *skb,
#else
static unsigned int ipt_acc_target(struct sk_buff **pskb,
#endif
                                   const struct net_device *in,
                                   const struct net_device *out,
                                   unsigned int hooknum,
#if LINUX_VERSION_CODE >= KERNEL_VERSION(2,6,17)
                                   const struct xt_target *target,
#endif
#if LINUX_VERSION_CODE >= KERNEL_VERSION(2,6,19)
                                   const void *targinfo)
#else
                                   const void *targinfo,
                                   void *userinfo)
#endif
{
    const struct ipt_acc_info *info = 
        (const struct ipt_acc_info *)targinfo;
#if LINUX_VERSION_CODE >= KERNEL_VERSION(2,6,24)
    u_int32_t src_ip = ip_hdr(skb)->saddr;
    u_int32_t dst_ip = ip_hdr(skb)->daddr;
    u_int32_t size = ntohs(ip_hdr(skb)->tot_len);
#else
#if LINUX_VERSION_CODE >= KERNEL_VERSION(2,6,22)
    u_int32_t src_ip = ip_hdr(*pskb)->saddr;
    u_int32_t dst_ip = ip_hdr(*pskb)->daddr;
    u_int32_t size = ntohs(ip_hdr(*pskb)->tot_len);
#else
    u_int32_t src_ip = (*pskb)->nh.iph->saddr;
    u_int32_t dst_ip = (*pskb)->nh.iph->daddr;
    u_int32_t size = ntohs((*pskb)->nh.iph->tot_len);
#endif
#endif

    spin_lock_bh(&ipt_acc_lock);

    if (ipt_acc_tables[info->table_nr].name[0] == 0) {
        printk("ACCOUNT: ipt_acc_target: Invalid table id %u. "
               "IPs %u.%u.%u.%u/%u.%u.%u.%u\n", info->table_nr, 
               NIPQUAD(src_ip), NIPQUAD(dst_ip));
        spin_unlock_bh(&ipt_acc_lock);
        return IPT_CONTINUE;
    }

    /* 8 bit network or "any" network */
    if (ipt_acc_tables[info->table_nr].depth == 0) {
        /* Count packet and check if the IP is new */
        ipt_acc_depth0_insert(
            (struct ipt_acc_mask_24 *)ipt_acc_tables[info->table_nr].data,
            ipt_acc_tables[info->table_nr].ip, 
            ipt_acc_tables[info->table_nr].netmask,
            src_ip, dst_ip, size, &ipt_acc_tables[info->table_nr].itemcount);
        spin_unlock_bh(&ipt_acc_lock);
        return IPT_CONTINUE;
    }

    /* 16 bit network */
    if (ipt_acc_tables[info->table_nr].depth == 1) {
        ipt_acc_depth1_insert(
            (struct ipt_acc_mask_16 *)ipt_acc_tables[info->table_nr].data,
            ipt_acc_tables[info->table_nr].ip, 
            ipt_acc_tables[info->table_nr].netmask,
            src_ip, dst_ip, size, &ipt_acc_tables[info->table_nr].itemcount);
        spin_unlock_bh(&ipt_acc_lock);
        return IPT_CONTINUE;
    }

    /* 24 bit network */
    if (ipt_acc_tables[info->table_nr].depth == 2) {
        ipt_acc_depth2_insert(
            (struct ipt_acc_mask_8 *)ipt_acc_tables[info->table_nr].data,
            ipt_acc_tables[info->table_nr].ip, 
            ipt_acc_tables[info->table_nr].netmask,
            src_ip, dst_ip, size, &ipt_acc_tables[info->table_nr].itemcount);
        spin_unlock_bh(&ipt_acc_lock);
        return IPT_CONTINUE;
    }

    printk("ACCOUNT: ipt_acc_target: Unable to process packet. "
           "Table id %u. IPs %u.%u.%u.%u/%u.%u.%u.%u\n", 
           info->table_nr, NIPQUAD(src_ip), NIPQUAD(dst_ip));

    spin_unlock_bh(&ipt_acc_lock);
    return IPT_CONTINUE;
}

/*
    Functions dealing with "handles":
    Handles are snapshots of a accounting state.
    
    read snapshots are only for debugging the code
    and are very expensive concerning speed/memory
    compared to read_and_flush.
    
    The functions aren't protected by spinlocks themselves
    as this is done in the ioctl part of the code.
*/

/*
    Find a free handle slot. Normally only one should be used,
    but there could be two or more applications accessing the data
    at the same time.
*/
static int ipt_acc_handle_find_slot(void)
{
    unsigned int i;
    /* Insert new table */
    for (i = 0; i < ACCOUNT_MAX_HANDLES; i++) {
        /* Found free slot */
        if (ipt_acc_handles[i].data == NULL) {
            /* Don't "mark" data as used as we are protected by a spinlock 
               by the calling function. handle_find_slot() is only a function
               to prevent code duplication. */
            return i;
        }
    }

    /* No free slot found */
    printk("ACCOUNT: No free handle slot found (max: %u). "
           "Please increase ACCOUNT_MAX_HANDLES.\n", ACCOUNT_MAX_HANDLES);
    return -1;
}

static int ipt_acc_handle_free(unsigned int handle)
{
    if (handle >= ACCOUNT_MAX_HANDLES) {
        printk("ACCOUNT: Invalid handle for ipt_acc_handle_free() specified:"
               " %u\n", handle);
        return -EINVAL;
    }

    ipt_acc_data_free(ipt_acc_handles[handle].data, 
                          ipt_acc_handles[handle].depth);
    memset (&ipt_acc_handles[handle], 0, sizeof (struct ipt_acc_handle));
    return 0;
}

/* Prepare data for read without flush. Use only for debugging!
   Real applications should use read&flush as it's way more efficent */
static int ipt_acc_handle_prepare_read(char *tablename,
         struct ipt_acc_handle *dest, u_int32_t *count)
{
    int table_nr=-1;
    unsigned char depth;

    for (table_nr = 0; table_nr < ACCOUNT_MAX_TABLES; table_nr++)
        if (strncmp(ipt_acc_tables[table_nr].name, tablename, 
            ACCOUNT_TABLE_NAME_LEN) == 0)
                break;

    if (table_nr == ACCOUNT_MAX_TABLES) {
        printk("ACCOUNT: ipt_acc_handle_prepare_read(): "
               "Table %s not found\n", tablename);
        return -1;
    }

    /* Fill up handle structure */
    dest->ip = ipt_acc_tables[table_nr].ip;
    dest->depth = ipt_acc_tables[table_nr].depth;
    dest->itemcount = ipt_acc_tables[table_nr].itemcount;

    /* allocate "root" table */
    if ((dest->data = ipt_acc_zalloc_page()) == NULL) {
        printk("ACCOUNT: out of memory for root table "
               "in ipt_acc_handle_prepare_read()\n");
        return -1;
    }

    /* Recursive copy of complete data structure */
    depth = dest->depth;
    if (depth == 0) {
        memcpy(dest->data, 
               ipt_acc_tables[table_nr].data, 
               sizeof(struct ipt_acc_mask_24));
    } else if (depth == 1) {
        struct ipt_acc_mask_16 *src_16 = 
            (struct ipt_acc_mask_16 *)ipt_acc_tables[table_nr].data;
        struct ipt_acc_mask_16 *network_16 =
            (struct ipt_acc_mask_16 *)dest->data;
        unsigned int b;

        for (b = 0; b <= 255; b++) {
            if (src_16->mask_24[b]) {
                if ((network_16->mask_24[b] = 
                     ipt_acc_zalloc_page()) == NULL) {
                    printk("ACCOUNT: out of memory during copy of 16 bit "
                           "network in ipt_acc_handle_prepare_read()\n");
                    ipt_acc_data_free(dest->data, depth);
                    return -1;
                }

                memcpy(network_16->mask_24[b], src_16->mask_24[b], 
                       sizeof(struct ipt_acc_mask_24));
            }
        }
    } else if(depth == 2) {
        struct ipt_acc_mask_8 *src_8 = 
            (struct ipt_acc_mask_8 *)ipt_acc_tables[table_nr].data;
        struct ipt_acc_mask_8 *network_8 = 
            (struct ipt_acc_mask_8 *)dest->data;
        struct ipt_acc_mask_16 *src_16, *network_16;
        unsigned int a, b;

        for (a = 0; a <= 255; a++) {
            if (src_8->mask_16[a]) {
                if ((network_8->mask_16[a] = 
                     ipt_acc_zalloc_page()) == NULL) {
                    printk("ACCOUNT: out of memory during copy of 24 bit network"
                           " in ipt_acc_handle_prepare_read()\n");
                    ipt_acc_data_free(dest->data, depth);
                    return -1;
                }

                memcpy(network_8->mask_16[a], src_8->mask_16[a], 
                       sizeof(struct ipt_acc_mask_16));

                src_16 = src_8->mask_16[a];
                network_16 = network_8->mask_16[a];

                for (b = 0; b <= 255; b++) {
                    if (src_16->mask_24[b]) {
                        if ((network_16->mask_24[b] = 
                             ipt_acc_zalloc_page()) == NULL) {
                            printk("ACCOUNT: out of memory during copy of 16 bit"
                                   " network in ipt_acc_handle_prepare_read()\n");
                            ipt_acc_data_free(dest->data, depth);
                            return -1;
                        }

                        memcpy(network_16->mask_24[b], src_16->mask_24[b], 
                               sizeof(struct ipt_acc_mask_24));
                    }
                }
            }
        }
    }

    *count = ipt_acc_tables[table_nr].itemcount;
    
    return 0;
}

/* Prepare data for read and flush it */
static int ipt_acc_handle_prepare_read_flush(char *tablename,
               struct ipt_acc_handle *dest, u_int32_t *count)
{
    int table_nr;
    void *new_data_page;

    for (table_nr = 0; table_nr < ACCOUNT_MAX_TABLES; table_nr++)
        if (strncmp(ipt_acc_tables[table_nr].name, tablename, 
            ACCOUNT_TABLE_NAME_LEN) == 0)
                break;

    if (table_nr == ACCOUNT_MAX_TABLES) {
        printk("ACCOUNT: ipt_acc_handle_prepare_read_flush(): "
               "Table %s not found\n", tablename);
        return -1;
    }

    /* Try to allocate memory */
    if (!(new_data_page = ipt_acc_zalloc_page())) {
        printk("ACCOUNT: ipt_acc_handle_prepare_read_flush(): "
               "Out of memory!\n");
        return -1;
    }

    /* Fill up handle structure */
    dest->ip = ipt_acc_tables[table_nr].ip;
    dest->depth = ipt_acc_tables[table_nr].depth;
    dest->itemcount = ipt_acc_tables[table_nr].itemcount;
    dest->data = ipt_acc_tables[table_nr].data;
    *count = ipt_acc_tables[table_nr].itemcount;

    /* "Flush" table data */
    ipt_acc_tables[table_nr].data = new_data_page;
    ipt_acc_tables[table_nr].itemcount = 0;

    return 0;
}

/* Copy 8 bit network data into a prepared buffer.
   We only copy entries != 0 to increase performance.
*/
static int ipt_acc_handle_copy_data(void *to_user, unsigned long *to_user_pos,
                                  unsigned long *tmpbuf_pos, 
                                  struct ipt_acc_mask_24 *data,
                                  u_int32_t net_ip, u_int32_t net_OR_mask)
{
    struct ipt_acc_handle_ip handle_ip;
    size_t handle_ip_size = sizeof (struct ipt_acc_handle_ip);
    unsigned int i;
    
    for (i = 0; i <= 255; i++) {
        if (data->ip[i].src_packets || data->ip[i].dst_packets) {
            handle_ip.ip = net_ip | net_OR_mask | (i<<24);
            
            handle_ip.src_packets = data->ip[i].src_packets;
            handle_ip.src_bytes = data->ip[i].src_bytes;
            handle_ip.dst_packets = data->ip[i].dst_packets;
            handle_ip.dst_bytes = data->ip[i].dst_bytes;

            /* Temporary buffer full? Flush to userspace */
            if (*tmpbuf_pos+handle_ip_size >= PAGE_SIZE) {
                if (copy_to_user(to_user + *to_user_pos, ipt_acc_tmpbuf,
                                                           *tmpbuf_pos))
                    return -EFAULT;
                *to_user_pos = *to_user_pos + *tmpbuf_pos;
                *tmpbuf_pos = 0;
            }
            memcpy(ipt_acc_tmpbuf+*tmpbuf_pos, &handle_ip, handle_ip_size);
            *tmpbuf_pos += handle_ip_size;
        }
    }
    
    return 0;
}
   
/* Copy the data from our internal structure 
   We only copy entries != 0 to increase performance.
   Overwrites ipt_acc_tmpbuf.
*/
static int ipt_acc_handle_get_data(u_int32_t handle, void *to_user)
{
    unsigned long to_user_pos=0, tmpbuf_pos=0;
    u_int32_t net_ip;
    unsigned char depth;

    if (handle >= ACCOUNT_MAX_HANDLES) {
        printk("ACCOUNT: invalid handle for ipt_acc_handle_get_data() "
               "specified: %u\n", handle);
        return -1;
    }

    if (ipt_acc_handles[handle].data == NULL) {
        printk("ACCOUNT: handle %u is BROKEN: Contains no data\n", handle);
        return -1;
    }

    net_ip = ipt_acc_handles[handle].ip;
    depth = ipt_acc_handles[handle].depth;

    /* 8 bit network */
    if (depth == 0) {
        struct ipt_acc_mask_24 *network = 
            (struct ipt_acc_mask_24*)ipt_acc_handles[handle].data;
        if (ipt_acc_handle_copy_data(to_user, &to_user_pos, &tmpbuf_pos,
                                     network, net_ip, 0))
            return -1;
        
        /* Flush remaining data to userspace */
        if (tmpbuf_pos)
            if (copy_to_user(to_user+to_user_pos, ipt_acc_tmpbuf, tmpbuf_pos))
                return -1;

        return 0;
    }

    /* 16 bit network */
    if (depth == 1) {
        struct ipt_acc_mask_16 *network_16 = 
            (struct ipt_acc_mask_16*)ipt_acc_handles[handle].data;
        unsigned int b;
        for (b = 0; b <= 255; b++) {
            if (network_16->mask_24[b]) {
                struct ipt_acc_mask_24 *network = 
                    (struct ipt_acc_mask_24*)network_16->mask_24[b];
                if (ipt_acc_handle_copy_data(to_user, &to_user_pos,
                                      &tmpbuf_pos, network, net_ip, (b << 16)))
                    return -1;
            }
        }

        /* Flush remaining data to userspace */
        if (tmpbuf_pos)
            if (copy_to_user(to_user+to_user_pos, ipt_acc_tmpbuf, tmpbuf_pos))
                return -1;

        return 0;
    }

    /* 24 bit network */
    if (depth == 2) {
        struct ipt_acc_mask_8 *network_8 = 
            (struct ipt_acc_mask_8*)ipt_acc_handles[handle].data;
        unsigned int a, b;
        for (a = 0; a <= 255; a++) {
            if (network_8->mask_16[a]) {
                struct ipt_acc_mask_16 *network_16 = 
                    (struct ipt_acc_mask_16*)network_8->mask_16[a];
                for (b = 0; b <= 255; b++) {
                    if (network_16->mask_24[b]) {
                        struct ipt_acc_mask_24 *network = 
                            (struct ipt_acc_mask_24*)network_16->mask_24[b];
                        if (ipt_acc_handle_copy_data(to_user,
                                       &to_user_pos, &tmpbuf_pos,
                                       network, net_ip, (a << 8) | (b << 16)))
                            return -1;
                    }
                }
            }
        }

        /* Flush remaining data to userspace */
        if (tmpbuf_pos)
            if (copy_to_user(to_user+to_user_pos, ipt_acc_tmpbuf, tmpbuf_pos))
                return -1;

        return 0;
    }
    
    return -1;
}

static int ipt_acc_set_ctl(struct sock *sk, int cmd, 
                               void *user, unsigned int len)
{
    struct ipt_acc_handle_sockopt handle;
    int ret = -EINVAL;

    if (!capable(CAP_NET_ADMIN))
        return -EPERM;

    switch (cmd) {
    case IPT_SO_SET_ACCOUNT_HANDLE_FREE:
        if (len != sizeof(struct ipt_acc_handle_sockopt)) {
            printk("ACCOUNT: ipt_acc_set_ctl: wrong data size (%u != %zu) "
                   "for IPT_SO_SET_HANDLE_FREE\n", 
                   len, sizeof(struct ipt_acc_handle_sockopt));
            break;
        }

        if (copy_from_user (&handle, user, len)) {
            printk("ACCOUNT: ipt_acc_set_ctl: copy_from_user failed for "
                   "IPT_SO_SET_HANDLE_FREE\n");
            break;
        }

        down(&ipt_acc_userspace_mutex);
        ret = ipt_acc_handle_free(handle.handle_nr);
        up(&ipt_acc_userspace_mutex);
        break;
    case IPT_SO_SET_ACCOUNT_HANDLE_FREE_ALL: {
            unsigned int i;
            down(&ipt_acc_userspace_mutex);
            for (i = 0; i < ACCOUNT_MAX_HANDLES; i++)
                ipt_acc_handle_free(i);
            up(&ipt_acc_userspace_mutex);
            ret = 0;
            break;
        }
    default:
        printk("ACCOUNT: ipt_acc_set_ctl: unknown request %i\n", cmd);
    }

    return ret;
}

static int ipt_acc_get_ctl(struct sock *sk, int cmd, void *user, int *len)
{
    struct ipt_acc_handle_sockopt handle;
    int ret = -EINVAL;

    if (!capable(CAP_NET_ADMIN))
        return -EPERM;

    switch (cmd) {
    case IPT_SO_GET_ACCOUNT_PREPARE_READ_FLUSH:
    case IPT_SO_GET_ACCOUNT_PREPARE_READ: {
            struct ipt_acc_handle dest;

            if (*len < sizeof(struct ipt_acc_handle_sockopt)) {
                printk("ACCOUNT: ipt_acc_get_ctl: wrong data size (%u != %zu) "
                    "for IPT_SO_GET_ACCOUNT_PREPARE_READ/READ_FLUSH\n",
                    *len, sizeof(struct ipt_acc_handle_sockopt));
                break;
            }

            if (copy_from_user (&handle, user, 
                                sizeof(struct ipt_acc_handle_sockopt))) {
                return -EFAULT;
                break;
            }

            spin_lock_bh(&ipt_acc_lock);
            if (cmd == IPT_SO_GET_ACCOUNT_PREPARE_READ_FLUSH)
                ret = ipt_acc_handle_prepare_read_flush(
                                    handle.name, &dest, &handle.itemcount);
            else
                ret = ipt_acc_handle_prepare_read(
                                    handle.name, &dest, &handle.itemcount);
            spin_unlock_bh(&ipt_acc_lock);
            // Error occured during prepare_read?
           if (ret == -1)
                return -EINVAL;

            /* Allocate a userspace handle */
            down(&ipt_acc_userspace_mutex);
            if ((handle.handle_nr = ipt_acc_handle_find_slot()) == -1) {
                ipt_acc_data_free(dest.data, dest.depth);
                up(&ipt_acc_userspace_mutex);
                return -EINVAL;
            }
            memcpy(&ipt_acc_handles[handle.handle_nr], &dest,
                             sizeof(struct ipt_acc_handle));
            up(&ipt_acc_userspace_mutex);

            if (copy_to_user(user, &handle, 
                            sizeof(struct ipt_acc_handle_sockopt))) {
                return -EFAULT;
                break;
            }
            ret = 0;
            break;
        }
    case IPT_SO_GET_ACCOUNT_GET_DATA:
        if (*len < sizeof(struct ipt_acc_handle_sockopt)) {
            printk("ACCOUNT: ipt_acc_get_ctl: wrong data size (%u != %zu)"
                   " for IPT_SO_GET_ACCOUNT_PREPARE_READ/READ_FLUSH\n",
                   *len, sizeof(struct ipt_acc_handle_sockopt));
            break;
        }

        if (copy_from_user (&handle, user, 
                            sizeof(struct ipt_acc_handle_sockopt))) {
            return -EFAULT;
            break;
        }

        if (handle.handle_nr >= ACCOUNT_MAX_HANDLES) {
            return -EINVAL;
            break;
        }

        if (*len < ipt_acc_handles[handle.handle_nr].itemcount
                   * sizeof(struct ipt_acc_handle_ip)) {
            printk("ACCOUNT: ipt_acc_get_ctl: not enough space (%u < %zu)"
                   " to store data from IPT_SO_GET_ACCOUNT_GET_DATA\n",
                   *len, ipt_acc_handles[handle.handle_nr].itemcount
                   * sizeof(struct ipt_acc_handle_ip));
            ret = -ENOMEM;
            break;
        }

        down(&ipt_acc_userspace_mutex);
        ret = ipt_acc_handle_get_data(handle.handle_nr, user);
        up(&ipt_acc_userspace_mutex);
        if (ret) {
            printk("ACCOUNT: ipt_acc_get_ctl: ipt_acc_handle_get_data"
                   " failed for handle %u\n", handle.handle_nr);
            break;
        }

        ret = 0;
        break;
    case IPT_SO_GET_ACCOUNT_GET_HANDLE_USAGE: {
            unsigned int i;
            if (*len < sizeof(struct ipt_acc_handle_sockopt)) {
                printk("ACCOUNT: ipt_acc_get_ctl: wrong data size (%u != %zu)"
                       " for IPT_SO_GET_ACCOUNT_GET_HANDLE_USAGE\n",
                       *len, sizeof(struct ipt_acc_handle_sockopt));
                break;
            }

            /* Find out how many handles are in use */
            handle.itemcount = 0;
            down(&ipt_acc_userspace_mutex);
            for (i = 0; i < ACCOUNT_MAX_HANDLES; i++)
                if (ipt_acc_handles[i].data)
                    handle.itemcount++;
            up(&ipt_acc_userspace_mutex);

            if (copy_to_user(user, &handle, 
                             sizeof(struct ipt_acc_handle_sockopt))) {
                return -EFAULT;
                break;
            }
            ret = 0;
            break;
        }
    case IPT_SO_GET_ACCOUNT_GET_TABLE_NAMES: {
            u_int32_t size = 0, i, name_len;
            char *tnames;

            spin_lock_bh(&ipt_acc_lock);

            /* Determine size of table names */
            for (i = 0; i < ACCOUNT_MAX_TABLES; i++) {
                if (ipt_acc_tables[i].name[0] != 0)
                    size += strlen (ipt_acc_tables[i].name) + 1;
            }
            size += 1;    /* Terminating NULL character */

            if (*len < size || size > PAGE_SIZE) {
                spin_unlock_bh(&ipt_acc_lock);
                printk("ACCOUNT: ipt_acc_get_ctl: not enough space (%u < %u < %lu)"
                       " to store table names\n", *len, size, PAGE_SIZE);
                ret = -ENOMEM;
                break;
            }
            /* Copy table names to userspace */
            tnames = ipt_acc_tmpbuf;
            for (i = 0; i < ACCOUNT_MAX_TABLES; i++) {
                if (ipt_acc_tables[i].name[0] != 0) {
                    name_len = strlen (ipt_acc_tables[i].name) + 1;
                    memcpy(tnames, ipt_acc_tables[i].name, name_len);
                    tnames += name_len;
                }
            }
            spin_unlock_bh(&ipt_acc_lock);

            /* Terminating NULL character */
            *tnames = 0;

            /* Transfer to userspace */
            if (copy_to_user(user, ipt_acc_tmpbuf, size))
                return -EFAULT;

            ret = 0;
            break;
        }
    default:
        printk("ACCOUNT: ipt_acc_get_ctl: unknown request %i\n", cmd);
    }

    return ret;
}

#if LINUX_VERSION_CODE >= KERNEL_VERSION(2,6,21)
static struct xt_target xt_acc_reg = {
#else
static struct ipt_target ipt_acc_reg = {
#endif
    .name = "ACCOUNT",
#if LINUX_VERSION_CODE >= KERNEL_VERSION(2,6,21)
    .family = AF_INET,
#endif
    .target = ipt_acc_target,
#if LINUX_VERSION_CODE >= KERNEL_VERSION(2,6,17)
    .targetsize = sizeof(struct ipt_acc_info),
#endif
    .checkentry = ipt_acc_checkentry,
    .destroy = ipt_acc_destroy,
    .me = THIS_MODULE
};

static struct nf_sockopt_ops ipt_acc_sockopts = {
    .pf = PF_INET,
    .set_optmin = IPT_SO_SET_ACCOUNT_HANDLE_FREE,
    .set_optmax = IPT_SO_SET_ACCOUNT_MAX+1,
    .set = ipt_acc_set_ctl,
    .get_optmin = IPT_SO_GET_ACCOUNT_PREPARE_READ,
    .get_optmax = IPT_SO_GET_ACCOUNT_MAX+1,
    .get = ipt_acc_get_ctl
};

static int __init init(void)
{
    init_MUTEX(&ipt_acc_userspace_mutex);

    if ((ipt_acc_tables = 
         kmalloc(ACCOUNT_MAX_TABLES * 
                 sizeof(struct ipt_acc_table), GFP_KERNEL)) == NULL) {
        printk("ACCOUNT: Out of memory allocating account_tables structure");
        goto error_cleanup;
    }
    memset(ipt_acc_tables, 0,
           ACCOUNT_MAX_TABLES * sizeof(struct ipt_acc_table));

    if ((ipt_acc_handles = 
         kmalloc(ACCOUNT_MAX_HANDLES * 
                 sizeof(struct ipt_acc_handle), GFP_KERNEL)) == NULL) {
        printk("ACCOUNT: Out of memory allocating account_handles structure");
        goto error_cleanup;
    }
    memset(ipt_acc_handles, 0,
           ACCOUNT_MAX_HANDLES * sizeof(struct ipt_acc_handle));

    /* Allocate one page as temporary storage */
    if ((ipt_acc_tmpbuf = (void*)__get_free_page(GFP_KERNEL)) == NULL) {
        printk("ACCOUNT: Out of memory for temporary buffer page\n");
        goto error_cleanup;
    }

    /* Register setsockopt */
    if (nf_register_sockopt(&ipt_acc_sockopts) < 0) {
        printk("ACCOUNT: Can't register sockopts. Aborting\n");
        goto error_cleanup;
    }

#if LINUX_VERSION_CODE >= KERNEL_VERSION(2,6,21)
    if (xt_register_target(&xt_acc_reg))
#else
    if (ipt_register_target(&ipt_acc_reg))
#endif
        goto error_cleanup;

    return 0;

error_cleanup:
    if(ipt_acc_tables)
        kfree(ipt_acc_tables);
    if(ipt_acc_handles)
        kfree(ipt_acc_handles);
    if (ipt_acc_tmpbuf)
        free_page((unsigned long)ipt_acc_tmpbuf);

    return -EINVAL;
}

static void __exit fini(void)
{
#if LINUX_VERSION_CODE >= KERNEL_VERSION(2,6,21)
    xt_unregister_target(&xt_acc_reg);
#else
    ipt_unregister_target(&ipt_acc_reg);
#endif

    nf_unregister_sockopt(&ipt_acc_sockopts);

    kfree(ipt_acc_tables);
    kfree(ipt_acc_handles);
    free_page((unsigned long)ipt_acc_tmpbuf);
}

module_init(init);
module_exit(fini);
MODULE_LICENSE("GPL");
