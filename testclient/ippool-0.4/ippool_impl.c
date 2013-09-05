/*****************************************************************************
 * Copyright (C) 2004 Katalix Systems Ltd
 * 
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 2 of the License, or
 * (at your option) any later version.
 * 
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 * 
 * You should have received a copy of the GNU General Public License
 * along with this program; if not, write to the Free Software
 * Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA 
 *
 *****************************************************************************/

/* Local IP pools.
 */

#include "usl.h"
#include "ippool_private.h"

#define IPPOOL_HASHBITS			5
#define IPPOOL_HASH_SIZE			((1 << IPPOOL_HASHBITS) - 1)

static struct usl_hlist_head ippool_list[1 << IPPOOL_HASHBITS];

static inline struct usl_hlist_head *ippool_name_hash(const char *pool_name)
{
	unsigned hash = usl_hash_full_name(pool_name, strlen(pool_name));
	return &ippool_list[hash & IPPOOL_HASH_SIZE];
}

struct ippool;

struct ippool_addrblock {
	struct ippool		*pool;		/* the pool owning this block */
	uint32_t		first_addr;	/* first address of block */
	int			num_addrs;	/* number of addresses in block */
	uint32_t		netmask;	/* constrains address range of block */
	struct usl_list_head	list; 		/* blocks may be chained together */
	int			rsvd_offset;	/* offset into use_map[] for reserved map */
	uint8_t			use_map[0];	/* variable length flags indicating 
						 * which addresses in block are allocated 
						 * or reserved */
};

struct ippool_stats {
	unsigned long		num_allocs;
	unsigned long		num_frees;
	unsigned long		num_alloc_fails;
};

struct ippool {
	const char		*pool_name;
	uint32_t		flags;
	uint32_t		trace;
	int			drain;
	struct usl_list_head	addr_block_list; /* list of address blocks in pool */
	struct usl_hlist_node	hlist;		/* list of IP pools */
	int			max_addrs;	/* max number of addresses, 0=unlimited */
	int			num_addrs;	/* total number of addresses assigned to pool */
	int			num_avail;	/* number of addresses available */
	struct ippool_stats 	stats;
	char			data[0];
};

static void ippool_log_maybe(struct ippool const *pool, int level, const char *fmt, ...)
{
	if ((pool != NULL) && (pool->trace)) {
		va_list ap;

		va_start(ap, fmt);
		ippool_vlog(level, fmt, ap);
		va_end(ap);
	}
}

static struct ippool *ippool_find(char *pool_name)
{
	struct ippool *pool;
	struct usl_hlist_node *walk;
	struct usl_hlist_node *tmp;

	usl_hlist_for_each(walk, tmp, ippool_name_hash(pool_name)) {
		pool = usl_hlist_entry(walk, struct ippool, hlist);
		if (strcmp(pool->pool_name, pool_name) == 0) {
			return pool;
		}
	}

	return NULL;
}

static inline int ippool_addrblock_offset(struct ippool_addrblock *block, uint32_t addr, int rsvd)
{
	if (rsvd) {
		return block->rsvd_offset + addr - block->first_addr;
	}
	return addr - block->first_addr;
}

static inline int ippool_addrblock_contains_addr(struct ippool_addrblock *block, uint32_t addr)
{
	if ((addr >= block->first_addr) && (addr < (block->first_addr + block->num_addrs))) {
		return 1;
	}

	return 0;
}

static int ippool_addrblock_is_addr_marked(struct ippool_addrblock *block, uint32_t addr, int rsvd)
{
	int offset;
	int byte_pos;
	int bit_pos;
	int result = 0;

	if (!((addr >= block->first_addr) && (addr < (block->first_addr + block->num_addrs)))) {
		goto out;
	}

	offset = ippool_addrblock_offset(block, addr, rsvd);
	byte_pos = offset / 8;
	bit_pos = offset % 8;

	result = (block->use_map[byte_pos] & (1 << bit_pos)) ? 1 : 0;

out:	
	return result;
}

static inline int ippool_addrblock_is_addr_available(struct ippool_addrblock *block, uint32_t addr)
{
	return !ippool_addrblock_is_addr_marked(block, addr, 0);
}

static inline int ippool_addrblock_is_addr_reserved(struct ippool_addrblock *block, uint32_t addr)
{
	return ippool_addrblock_is_addr_marked(block, addr, 1);
}

static int ippool_addrblock_set_addr_in_use(struct ippool_addrblock *block, uint32_t addr, int in_use, int rsvd)
{
	int offset;
	int byte_pos;
	int bit_pos;
	int result = 0;

	if (!((addr >= block->first_addr) && (addr < (block->first_addr + block->num_addrs)))) {
		result = -EINVAL;
		goto out;
	}

	offset = ippool_addrblock_offset(block, addr, rsvd);
	byte_pos = offset / 8;
	bit_pos = offset % 8;
	
	if (in_use) {
		block->use_map[byte_pos] |= (1 << bit_pos);
	} else {
		block->use_map[byte_pos] &= ~(1 << bit_pos);
	}

out:
	return result;
}

int ippool_addr_get(char *pool_name, struct in_addr *result_addr)
{
	struct ippool *pool;
	struct ippool_addrblock *block;
	struct usl_list_head *walk;
	struct usl_list_head *tmp;
	uint32_t addr;
	int result = 0;
	struct in_addr in_addr;

	pool = ippool_find(pool_name);
	if (pool == NULL) {
		result = -ENOENT;
		goto out;
	}

	if (pool->drain) {
		result = -EPERM;
		ippool_log_maybe(pool, LOG_WARNING, "POOL: %s: address allocation administratively disabled", pool->pool_name);
		goto out;
	}

	usl_list_for_each(walk, tmp, &pool->addr_block_list) {
		block = usl_list_entry(walk, struct ippool_addrblock, list);
		for (addr = block->first_addr; addr < (block->first_addr + block->num_addrs); addr++) {
			if (ippool_addrblock_is_addr_available(block, addr)) {
				/* Mark the address as used */
				ippool_addrblock_set_addr_in_use(block, addr, 1, 0);
				pool->stats.num_allocs++;
				pool->num_avail--;
				in_addr.s_addr = htonl(addr);
				result_addr->s_addr = in_addr.s_addr;
				ippool_log_maybe(pool, LOG_DEBUG, "POOL: %s: allocated address %s", pool->pool_name, inet_ntoa(in_addr));
				goto out;
			}
		}
	}

	ippool_log_maybe(pool, LOG_WARNING, "POOL: %s: address allocation failed", pool->pool_name);
	pool->stats.num_alloc_fails++;
	result = -EMFILE;
out:
	return result;
}

int ippool_addr_put(char *pool_name, struct in_addr addr)
{
	struct ippool *pool;
	struct ippool_addrblock *block;
	struct usl_list_head *walk;
	struct usl_list_head *tmp;
	uint32_t put_addr = ntohl(addr.s_addr);
	int result = 0;

	pool = ippool_find(pool_name);
	if (pool == NULL) {
		result = -ENOENT;
		goto out;
	}

	usl_list_for_each(walk, tmp, &pool->addr_block_list) {
		block = usl_list_entry(walk, struct ippool_addrblock, list);
		if (ippool_addrblock_contains_addr(block, put_addr)) {
			if (!ippool_addrblock_is_addr_available(block, put_addr)) {
				/* Mark the address as free */
				ippool_addrblock_set_addr_in_use(block, put_addr, 0, 0);
				pool->stats.num_frees++;
				pool->num_avail++;
				ippool_log_maybe(pool, LOG_DEBUG, "POOL: %s: freed address %s", pool->pool_name, inet_ntoa(addr));
				goto out;
			}
		}
	}

	ippool_log_maybe(pool, LOG_WARNING, "POOL: %s: free address %s failed", pool->pool_name, inet_ntoa(addr));
	result = -EINVAL;

out:
	return result;
}

static int ippool_addrblock_add(struct ippool *pool, uint32_t first_addr, int num_addrs, uint32_t netmask)
{
	struct ippool_addrblock *block;
	struct usl_list_head *walk;
	struct usl_list_head *tmp;
	int result = 0;
	int block_size;
	uint32_t addr;
	uint32_t max_addrs;

	/* Check for overlapping address blocks */
	usl_list_for_each(walk, tmp, &pool->addr_block_list) {
		block = usl_list_entry(walk, struct ippool_addrblock, list);
		if (((first_addr >= block->first_addr) && (first_addr < (block->first_addr + num_addrs))) ||
		    (((first_addr + num_addrs) >= block->first_addr) && ((first_addr + num_addrs) < (block->first_addr + block->num_addrs)))) {
			result = -EEXIST;
			goto out;
		}
	}

	/* By default, assign all addresses within in the netmask to the pool */
	max_addrs = ~netmask - (first_addr & ~netmask) + 1;
	if (num_addrs == 0) {
		num_addrs = max_addrs;
	}

	/* Limit number of addresses in block to specified netmask & first_addr */
	if (num_addrs > max_addrs) {
		num_addrs = max_addrs;
	}

	/* Don't allow crazy address block sizes */
	if (num_addrs > 0xffff) {
		num_addrs = 0xffff;
	}

	/* Check that max pool size won't be exceeded */
	if ((pool->max_addrs > 0) && 
	    ((pool->num_addrs + num_addrs) > pool->max_addrs)) {
		result = -EMFILE;
		goto out;
	}

	/* Allocate new block.
	 * Each block has a variable length use_map[] which consists of two bits per address,
	 * indicating whether the address is in use or whether it has been reserved by the
	 * operator. use_map[] is arranged as two separate bit-arrays. block->rsvd_offset
	 * tells where the reserved address array starts.
	 */
	block_size = sizeof(*block) + (((num_addrs / 8)  + 1) * 2);
	block = malloc(block_size);
	if (block == NULL) {
		result = -ENOMEM;
		goto out;
	}
	memset(block, 0, block_size);
	block->first_addr = first_addr;
	block->num_addrs = num_addrs;
	block->netmask = netmask;
	block->pool = pool;
	block->rsvd_offset = num_addrs + 1;;

	pool->num_addrs += num_addrs;
	pool->num_avail += num_addrs;

	/* Mark addresses as used if they are illegal. Illegal addresses are those
	 * that are the network or broadcast address, calculated from the block's
	 * netmask. Note that the addresses are marked only in the in_use map, not
	 * the reserved address map.
	 */
	for (addr = block->first_addr; addr < (block->first_addr + block->num_addrs); addr++) {
		if (((addr & ~netmask) == 0) || ((addr & ~netmask) == ~netmask)) {
			ippool_addrblock_set_addr_in_use(block, addr, 1, 0);
			pool->num_avail--;
		}
	}

	/* and add it to the pool's block list */
	USL_LIST_HEAD_INIT(&block->list);
	usl_list_add_tail(&block->list, &pool->addr_block_list);

out:
	return result;
}

static int ippool_addrblock_reserve(struct ippool *pool, uint32_t first_addr, int num_addrs, uint32_t netmask, int reserve)
{
	struct ippool_addrblock *block;
	struct usl_list_head *walk;
	struct usl_list_head *tmp;
	int result = 0;
	uint32_t addr;

	/* By default, reserve/unreserve all addresses in the block */
	if (num_addrs == 0) {
		num_addrs = ~netmask - (first_addr & ~netmask) + 1;
	}

	for (addr = first_addr; addr < (first_addr + num_addrs); addr++) {
		/* Skip network and broadcast addresses */
		if ((addr & ~netmask) == 0) {
			continue;
		}
		if ((addr & ~netmask) == ~netmask) {
			break;
		}

		/* Find the block containing the address */
		usl_list_for_each(walk, tmp, &pool->addr_block_list) {
			block = usl_list_entry(walk, struct ippool_addrblock, list);
			if (ippool_addrblock_contains_addr(block, addr)) {
				if (reserve) {
					if (ippool_addrblock_is_addr_available(block, addr)) {
						/* Mark the address as used in both maps */
						ippool_addrblock_set_addr_in_use(block, addr, 1, 0);
						ippool_addrblock_set_addr_in_use(block, addr, 1, 1);
						pool->num_avail--;
					}
				} else {
					if (!ippool_addrblock_is_addr_available(block, addr)) {
						/* Mark the address as unused in both maps */
						ippool_addrblock_set_addr_in_use(block, addr, 0, 0);
						ippool_addrblock_set_addr_in_use(block, addr, 0, 1);
						pool->num_avail++;
					}
				}
			}
		}
		
	}

	return result;
}

/* This does not allow removing a partial block 
 */
static int ippool_addrblock_remove(struct ippool *pool, uint32_t first_addr, int num_addrs)
{
	struct ippool_addrblock *block;
	struct usl_list_head *walk;
	struct usl_list_head *tmp;
	int result = 0;

	/* Find the block containing the address */
	usl_list_for_each(walk, tmp, &pool->addr_block_list) {
		block = usl_list_entry(walk, struct ippool_addrblock, list);
		/* first_addr & num_addrs must match */ 
		if ((block->first_addr == first_addr) && (block->num_addrs == num_addrs)) {
			ippool_addrblock_reserve(pool, first_addr, num_addrs, block->netmask, 1);
			pool->num_addrs -= num_addrs;
			usl_list_del(&block->list);
			free(block);
			goto out;
		}
	}

	result = -ENOENT;

out:
	return result;
}

/* Return start/end of contiguous address range starting at address addr.
 * Used to obtain either a list of unused addresses or a list of resrved 
 * addresses.
 */
static int ippool_addr_range_match(struct ippool *pool, int block_num, uint32_t addr, uint32_t *start, uint32_t *end, int rsvd)
{
	struct ippool_addrblock *block;
	struct usl_list_head *walk;
	struct usl_list_head *tmp;
	int result = -EINVAL;
	uint32_t reg_start = 0;
	uint32_t reg_end = 0;
	int block_index = 0;
	int (*addr_match)(struct ippool_addrblock *block, uint32_t addr);

	/* Allows caller to differentiate address out of range versus
	 * block out of range.
	 */
	if ((addr == 0) && (block_num != 0)) {
		result = -ENOENT;
	}

	addr_match = rsvd ? ippool_addrblock_is_addr_reserved : ippool_addrblock_is_addr_available;

	/* Find the block containing the address. If addr is 0, use first address
	 * of specified block.
	 */
	usl_list_for_each(walk, tmp, &pool->addr_block_list) {
		block = usl_list_entry(walk, struct ippool_addrblock, list);
		block_index++;
		if ((addr == 0) && (block_num != 0)) {
			if (block_index == block_num) {
				addr = block->first_addr;
			} else {
				continue;
			}
		}
		if (ippool_addrblock_contains_addr(block, addr)) {
			/* Starting at addr, find the start/end of contiguous addresses
			 * that are matched.
			 */
			reg_end = block->first_addr + block->num_addrs - 1;
			for (; addr < (block->first_addr + block->num_addrs); addr++) {
				if ((*addr_match)(block, addr)) {
					if (reg_start == 0) {
						reg_start = addr;
					}
				} else {
					if (reg_start != 0) {
						reg_end = addr - 1;
						goto out;
					}
				}
			}
		}
	}
out:
	if (reg_start != 0) {
		*start = reg_start;
		*end = reg_end;
		result = 0;
	}

	return result;
}

static int ippool_create(char *pool_name, struct ippool **new_pool)
{
	int result = 0;
	struct ippool *pool;
	int pool_name_len = 0;
	int pool_alloc_size;

	if ((pool_name_len = strlen(pool_name)) == 0) {
		result = -EINVAL;
		goto out;
	}

	pool = ippool_find(pool_name);
	if (pool != NULL) {
		result = -EEXIST;
		goto out;
	}

	pool_alloc_size = sizeof(struct ippool) + pool_name_len + 1;
	pool = malloc(pool_alloc_size);
	if (pool == NULL) {
		result = -ENOMEM;
		goto out;
	}
	memset(pool, 0, pool_alloc_size);
	USL_LIST_HEAD_INIT(&pool->addr_block_list);
	USL_HLIST_NODE_INIT(&pool->hlist);
	strcpy(&pool->data[0], pool_name);
	pool->pool_name = &pool->data[0];

	usl_hlist_add_head(&pool->hlist, ippool_name_hash(pool_name));
	*new_pool = pool;

out:
	return result;
}

static int ippool_delete(char *pool_name, struct ippool *pool)
{
	struct ippool_addrblock *block;
	struct usl_list_head *walk;
	struct usl_list_head *tmp;
	int result = 0;

	if (pool == NULL) {
		pool = ippool_find(pool_name);
		if (pool == NULL) {
			result = -ENOENT;
			goto out;
		}
	} else {
		pool_name = (char *) pool->pool_name;
	}

	pool->num_addrs = 0;

	/* Delete each block, don't care if addresses are allocated */
	usl_list_for_each(walk, tmp, &pool->addr_block_list) {
		block = usl_list_entry(walk, struct ippool_addrblock, list);
		usl_list_del(&block->list);
		free(block);
	}

	usl_hlist_del(&pool->hlist);
	free(pool);

out:
	if (result == 0) {
		ippool_log_maybe(pool, LOG_DEBUG, "POOL: %s: deleted", pool_name);
	} else {
		ippool_log_maybe(pool, LOG_ERR, "POOL: %s: delete failed, result=%d", pool_name, result);
	}

	return result;
}

static int ippool_modify(char *pool_name, struct ippool *pool, struct ippool_api_pool_msg_data *msg)
{
	int result = 0;

	if (pool == NULL) {
		pool = ippool_find(pool_name);
		if (pool == NULL) {
			result = -ENOENT;
			goto out;
		}
	} else {
		pool_name = (char *) pool->pool_name;
	}

	if (msg->flags & IPPOOL_API_FLAG_TRACE) {
		pool->trace = msg->trace;
		ippool_log_maybe(pool, LOG_WARNING, "POOL: %s: set trace %s", pool_name, msg->trace ? "ON" : "OFF");
	}
	if (msg->flags & IPPOOL_API_FLAG_DRAIN) {
		pool->drain = msg->drain;
		ippool_log_maybe(pool, LOG_WARNING, "POOL: %s: set drain %s", pool_name, msg->drain ? "ON" : "OFF");
	}
	if (msg->flags & IPPOOL_API_FLAG_MAX_ADDRS) {
		pool->max_addrs = msg->max_addrs;
		ippool_log_maybe(pool, LOG_WARNING, "POOL: %s: set max_addrs=%d", pool_name, msg->max_addrs);
	}

	pool->flags |= msg->flags;

out:
	return result;
}

/*****************************************************************************
 * Management interface
 *****************************************************************************/

bool_t ippool_create_1_svc(struct ippool_api_pool_msg_data msg, int *result, struct svc_req *req)
{
	int block;
	struct ippool *pool = NULL;

	IPPOOL_DEBUG("%s: pool: %s", __FUNCTION__, msg.pool_name);

	if (strlen(msg.pool_name) == 0) {
		*result = -EINVAL;
		goto out;
	}

	*result = ippool_create(msg.pool_name, &pool);
	if (*result < 0) {
		goto out;
	}

	for (block = 0; block < msg.addr_block.addr_block_len; block++) {
		if (msg.addr_block.addr_block_val[block].first_addr.s_addr == 0) {
			*result = -EINVAL;
			goto out;
		}
		if (msg.addr_block.addr_block_val[block].netmask.s_addr == 0) {
			msg.addr_block.addr_block_val[block].netmask.s_addr = htonl(IPPOOL_API_DEFAULT_NETMASK);
		}
		*result = ippool_addrblock_add(pool, 
						    ntohl(msg.addr_block.addr_block_val[block].first_addr.s_addr), 
						    msg.addr_block.addr_block_val[block].num_addrs, 
						    ntohl(msg.addr_block.addr_block_val[block].netmask.s_addr));
		if (*result < 0) {
			goto out;
		}
	}

	*result = ippool_modify(NULL, pool, &msg);
	if (*result < 0) {
		(void) ippool_delete(NULL, pool);
		goto out;
	}

	pool->flags |= msg.flags;

out:
	if (*result == 0) {
		ippool_log_maybe(pool, LOG_DEBUG, "POOL: %s: created", msg.pool_name);
	} else {
		if (pool != NULL) {
			(void) ippool_delete(NULL, pool);
		}
		ippool_log_maybe(pool, LOG_ERR, "POOL: %s: create failed, result=%d", msg.pool_name, *result);
	}

	return TRUE;
}

bool_t ippool_delete_1_svc(char *pool_name, int *result, struct svc_req *req)
{
	IPPOOL_DEBUG("%s: pool: %s", __FUNCTION__, pool_name);

	if (strlen(pool_name) == 0) {
		*result = -EINVAL;
		goto out;
	}

	*result = ippool_delete(pool_name, NULL);

out:
	return TRUE;
}

bool_t ippool_modify_1_svc(struct ippool_api_pool_msg_data msg, int *result, struct svc_req *req)
{
	struct ippool *pool;

	IPPOOL_DEBUG("%s: pool: %s", __FUNCTION__, msg.pool_name);

	if (strlen(msg.pool_name) == 0) {
		*result = -EINVAL;
		goto out;
	}

	pool = ippool_find(msg.pool_name);
	if (pool == NULL) {
		*result = -ENOENT;
		goto out;
	}

	*result = ippool_modify(NULL, pool, &msg);

out:
	if (*result == 0) {
		ippool_log_maybe(pool, LOG_DEBUG, "POOL: %s: modified", msg.pool_name);
	} else {
		ippool_log_maybe(pool, LOG_ERR, "POOL: %s: modify failed, result=%d", msg.pool_name, *result);
	}

	return TRUE;
}

bool_t ippool_get_1_svc(char *pool_name, struct ippool_api_pool_msg_data *result, struct svc_req *req)
{
	struct ippool *pool;
	struct ippool_addrblock *block;
	struct usl_list_head *walk;
	struct usl_list_head *tmp;
	int num_blocks;
	int block_index;
	int index;

	IPPOOL_DEBUG("%s: pool: %s", __FUNCTION__, pool_name);

	memset(result, 0, sizeof(*result));

	if (strlen(pool_name) == 0) {
		result->result_code = -EINVAL;
		goto out;
	}

	pool = ippool_find(pool_name);
	if (pool == NULL) {
		result->result_code = -ENOENT;
		goto out;
	}

	result->pool_name = strdup(pool->pool_name);
	if (result->pool_name == NULL) {
		goto error;
	}		
	result->flags = pool->flags;
	result->trace = pool->trace;
	result->drain = pool->drain;
	result->max_addrs = pool->max_addrs;
	result->num_addrs = pool->num_addrs;
	result->num_avail = pool->num_avail;
	result->stats.num_allocs = pool->stats.num_allocs;
	result->stats.num_frees = pool->stats.num_frees;
	result->stats.num_alloc_fails = pool->stats.num_alloc_fails;

	/* Count the number of address blocks */
	num_blocks = 0;
	usl_list_for_each(walk, tmp, &pool->addr_block_list) {
		num_blocks++;
	}

	/* Allocate array to return array of address blocks */
	result->addr_block.addr_block_len = 0;
	if (num_blocks > 0) {
		result->addr_block.addr_block_val = calloc(num_blocks, sizeof(struct ippool_addrblock));
		if (result->addr_block.addr_block_val == NULL) {
			result->result_code = -ENOMEM;
			goto out;
		}
		result->addr_block.addr_block_len = num_blocks;

		block_index = 0;
		usl_list_for_each(walk, tmp, &pool->addr_block_list) {
			block = usl_list_entry(walk, struct ippool_addrblock, list);
			result->addr_block.addr_block_val[block_index].first_addr.s_addr = htonl(block->first_addr);
			result->addr_block.addr_block_val[block_index].num_addrs = block->num_addrs;
			result->addr_block.addr_block_val[block_index].netmask.s_addr = htonl(block->netmask);
			block_index++;
		}
	}

	/* Count the number of blocks of contiguous reserved addresses */
	num_blocks = 0;
	for (index = 1; index; index++) {
		uint32_t addr = 0;
		uint32_t start;
		uint32_t end;
		int ret;
		do {
			ret = ippool_addr_range_match(pool, index, addr, &start, &end, 1);
			if (ret < 0) {
				break;
			}
			num_blocks++;
			addr = end + 1;
			continue;
		} while (ret == 0);

		if (ret == -ENOENT) {
			break;
		}
	}

	/* Allocate array to return array of contiguous reserved addresses */
	result->rsvd_block.rsvd_block_len = 0;
	if (num_blocks > 0) {
		result->rsvd_block.rsvd_block_val = calloc(num_blocks, sizeof(struct ippool_addrblock));
		if (result->rsvd_block.rsvd_block_val == NULL) {
			result->result_code = -ENOMEM;
			goto out;
		}
		result->rsvd_block.rsvd_block_len = num_blocks;

		block_index = 0;
		for (index = 1; index; index++) {
			uint32_t addr = 0;
			uint32_t start;
			uint32_t end;
			int ret;
			if (block_index == num_blocks) {
				break;
			}
			do {
				ret = ippool_addr_range_match(pool, index, addr, &start, &end, 1);
				if (ret < 0) {
					break;
				}
				result->rsvd_block.rsvd_block_val[block_index].first_addr.s_addr = htonl(start);
				result->rsvd_block.rsvd_block_val[block_index].num_addrs = end - start + 1;
				result->rsvd_block.rsvd_block_val[block_index].netmask.s_addr = htonl(block->netmask);
				addr = end + 1;
				block_index++;
				continue;
			} while (ret == 0);

			if (ret == -ENOENT) {
				break;
			}
		}
	}

	/* Count the number of blocks of contiguous available addresses */
	num_blocks = 0;
	for (index = 1; index; index++) {
		uint32_t addr = 0;
		uint32_t start;
		uint32_t end;
		int ret;
		do {
			ret = ippool_addr_range_match(pool, index, addr, &start, &end, 0);
			if (ret < 0) {
				break;
			}
			num_blocks++;
			addr = end + 1;
			continue;
		} while (ret == 0);

		if (ret == -ENOENT) {
			break;
		}
	}

	/* Allocate array to return array of contiguous available addresses */
	result->avail_block.avail_block_len = 0;
	if (num_blocks > 0) {
		result->avail_block.avail_block_val = calloc(num_blocks, sizeof(struct ippool_addrblock));
		if (result->avail_block.avail_block_val == NULL) {
			result->result_code = -ENOMEM;
			goto out;
		}
		result->avail_block.avail_block_len = num_blocks;

		block_index = 0;
		for (index = 1; index; index++) {
			uint32_t addr = 0;
			uint32_t start;
			uint32_t end;
			int ret;
			if (block_index == num_blocks) {
				break;
			}
			do {
				ret = ippool_addr_range_match(pool, index, addr, &start, &end, 0);
				if (ret < 0) {
					break;
				}
				result->avail_block.avail_block_val[block_index].first_addr.s_addr = htonl(start);
				result->avail_block.avail_block_val[block_index].num_addrs = end - start + 1;
				result->avail_block.avail_block_val[block_index].netmask.s_addr = htonl(block->netmask);
				addr = end + 1;
				block_index++;
				continue;
			} while (ret == 0);

			if (ret == -ENOENT) {
				break;
			}
		}
	}


	result->result_code = 0;
out:
	/* strings must be filled in in the response */
	if (result->pool_name == NULL) {
		result->pool_name = strdup(pool_name);
		if (result->pool_name == NULL) {
			goto error;
		}
	}

	return TRUE;

error:
	return FALSE;
}

bool_t ippool_list_1_svc(struct ippool_api_pool_list_msg_data *result, struct svc_req *req)
{
	struct usl_hlist_node *walk;
	struct usl_hlist_node *tmp;
	struct ippool *pool;
	struct ippool_api_pool_list_entry *entry;
	struct ippool_api_pool_list_entry *tmpe;
	int num_pools = 0;
	int hash_index;

	IPPOOL_DEBUG("%s: enter", __FUNCTION__);

	memset(result, 0, sizeof(*result));

	result->pools = calloc(1, sizeof(*result->pools));
	if (result->pools == NULL) {
		result->result = -ENOMEM;
		goto error;
	}
	entry = result->pools;

	for (hash_index = 0; hash_index < IPPOOL_HASH_SIZE; hash_index++) {
		usl_hlist_for_each(walk, tmp, &ippool_list[hash_index]) {
			pool = usl_hlist_entry(walk, struct ippool, hlist);

			entry->pool_name = strdup(pool->pool_name);
			if (entry->pool_name == NULL) {
				result->result = -ENOMEM;
				goto error;
			}

			tmpe = calloc(1, sizeof(*result->pools));
			if (tmpe == NULL) {
				result->result = -ENOMEM;
				goto error;
			}
			entry->next = tmpe;
			entry = tmpe;
			num_pools++;
		}
	}

	entry->pool_name = strdup("");
	if (entry->pool_name == NULL) {
		goto error;
	}

	result->num_pools = num_pools;

	return TRUE;

error:
	for (entry = result->pools; entry != NULL; ) {
		tmpe = entry->next;
		free(entry->pool_name);
		free(entry);
		entry = tmpe;
	}

	return TRUE;
}

bool_t ippool_addrblock_add_1_svc(char *pool_name, struct ippool_api_addrblock range, int *result, struct svc_req *req)
{
	struct ippool *pool;
	struct in_addr addr;
	uint32_t netmask;

	IPPOOL_DEBUG("%s: pool: %s", __FUNCTION__, pool_name);

	if (strlen(pool_name) == 0) {
		*result = -EINVAL;
		goto out;
	}

	pool = ippool_find(pool_name);
	if (pool == NULL) {
		*result = -ENOENT;
		goto out;
	}

	netmask = ntohl(range.netmask.s_addr);
	if (netmask == 0) {
		netmask = IPPOOL_API_DEFAULT_NETMASK;
	}

	*result = ippool_addrblock_add(pool, ntohl(range.first_addr.s_addr), range.num_addrs, netmask);

out:
	addr.s_addr = range.first_addr.s_addr;
	if (*result == 0) {
		ippool_log_maybe(pool, LOG_DEBUG, "POOL: %s: added address block %s, size %d", pool_name,
				inet_ntoa(addr), range.num_addrs);
	} else {
		ippool_log_maybe(pool, LOG_ERR, "POOL: %s: address block add failed, %s, size %d, result=%d", pool_name, 
				inet_ntoa(addr), range.num_addrs, *result);
	}

	return TRUE;
}

bool_t ippool_addrblock_remove_1_svc(char *pool_name, struct ippool_api_addrblock range, int *result, struct svc_req *req)
{
	struct ippool *pool;
	struct in_addr addr;

	IPPOOL_DEBUG("%s: pool: %s", __FUNCTION__, pool_name);

	if (strlen(pool_name) == 0) {
		*result = -EINVAL;
		goto out;
	}

	pool = ippool_find(pool_name);
	if (pool == NULL) {
		*result = -ENOENT;
		goto out;
	}

	*result = ippool_addrblock_remove(pool, ntohl(range.first_addr.s_addr), range.num_addrs);

out:
	addr.s_addr = range.first_addr.s_addr;
	if (*result == 0) {
		ippool_log_maybe(pool, LOG_DEBUG, "POOL: %s: removed address block %s, size %d", pool_name,
				inet_ntoa(addr), range.num_addrs);
	} else {
		ippool_log_maybe(pool, LOG_ERR, "POOL: %s: address block remove failed, %s, size %d, result=%d", pool_name, 
				inet_ntoa(addr), range.num_addrs, *result);
	}

	return TRUE;
}

bool_t ippool_addrblock_reserve_1_svc(char *pool_name, struct ippool_api_addrblock range, int *result, struct svc_req *req)
{
	struct ippool *pool;
	struct in_addr addr;

	IPPOOL_DEBUG("%s: pool: %s", __FUNCTION__, pool_name);

	if (strlen(pool_name) == 0) {
		*result = -EINVAL;
		goto out;
	}

	pool = ippool_find(pool_name);
	if (pool == NULL) {
		*result = -ENOENT;
		goto out;
	}

	*result = ippool_addrblock_reserve(pool, ntohl(range.first_addr.s_addr), range.num_addrs, ntohl(range.netmask.s_addr), 1);

out:
	addr.s_addr = range.first_addr.s_addr;
	if (*result == 0) {
		ippool_log_maybe(pool, LOG_DEBUG, "POOL: %s: reserved address block %s, size %d", pool_name,
				inet_ntoa(addr), range.num_addrs);
	} else {
		ippool_log_maybe(pool, LOG_ERR, "POOL: %s: reserve address block failed, %s, size %d, result=%d", pool_name, 
				inet_ntoa(addr), range.num_addrs, *result);
	}

	return TRUE;
}

bool_t ippool_addrblock_unreserve_1_svc(char *pool_name, struct ippool_api_addrblock range, int *result, struct svc_req *req)
{
	struct ippool *pool;
	struct in_addr addr;

	IPPOOL_DEBUG("%s: pool: %s", __FUNCTION__, pool_name);

	if (strlen(pool_name) == 0) {
		*result = -EINVAL;
		goto out;
	}

	pool = ippool_find(pool_name);
	if (pool == NULL) {
		*result = -ENOENT;
		goto out;
	}

	*result = ippool_addrblock_reserve(pool, ntohl(range.first_addr.s_addr), range.num_addrs, ntohl(range.netmask.s_addr), 0);

out:
	addr.s_addr = range.first_addr.s_addr;
	if (*result == 0) {
		ippool_log_maybe(pool, LOG_DEBUG, "POOL: %s: unreserved address block %s, size %d", pool_name,
				inet_ntoa(addr), range.num_addrs);
	} else {
		ippool_log_maybe(pool, LOG_ERR, "POOL: %s: address block unreserve failed, %s, size %d, result=%d", pool_name, 
				inet_ntoa(addr), range.num_addrs, *result);
	}

	return TRUE;
}

bool_t ippool_addr_alloc_1_svc(char *pool_name, struct ippool_api_addr_alloc_msg_data *result, struct svc_req *req)
{
	struct in_addr addr = { INADDR_ANY, };

	IPPOOL_DEBUG("%s: pool: %s", __FUNCTION__, pool_name);

	result->result_code = ippool_addr_get(pool_name, &addr);
	if (result->result_code == 0) {
		result->addr.s_addr = addr.s_addr;
	}

	return TRUE;
}

bool_t ippool_addr_free_1_svc(char *pool_name, struct ippool_api_ip_addr addr, int *result, struct svc_req *req)
{
	struct in_addr free_addr;

	IPPOOL_DEBUG("%s: pool: %s", __FUNCTION__, pool_name);

	free_addr.s_addr = addr.s_addr;
	*result = ippool_addr_put(pool_name, free_addr);

	return TRUE;
}

/*****************************************************************************
 * Init and cleanup
 *****************************************************************************/

void ippool_init(void)
{
}

void ippool_cleanup(void)
{
	struct usl_hlist_node *walk;
	struct usl_hlist_node *tmp;
	struct ippool *pool;
	int hash_index;

	for (hash_index = 0; hash_index < IPPOOL_HASH_SIZE; hash_index++) {
		usl_hlist_for_each(walk, tmp, &ippool_list[hash_index]) {
			pool = usl_hlist_entry(walk, struct ippool, hlist);
			ippool_delete(NULL, pool);
		}
	}
}
