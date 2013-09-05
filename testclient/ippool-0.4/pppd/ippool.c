/* ippool.c - pppd plugin to access IP address pool maintained externally.
 */

#include <unistd.h>
#include <string.h>
#include <stdlib.h>
#include <errno.h>
#include "pppd.h"
#include "pathnames.h"
#include "fsm.h" /* Needed for lcp.h to include cleanly */
#include "lcp.h"
#include "ccp.h"
#include "ipcp.h"
#include <sys/stat.h>
#include <net/if.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <signal.h>

#include <linux/types.h>

#include "ippool_rpc.h"

const char pppd_version[] = VERSION;

static int ippool_fd = -1;
static char *ippool_pool_name = NULL;
static char *ippool_pool_name2 = NULL;
static char *ippool_server = "localhost";
static int ippool_debug = 0;
static struct in_addr ippool_addr[2];


static option_t ippool_options[] = {
	{ "ippool_name", o_string, &ippool_pool_name,
	  "IP pool name" }, 
	{ "ippool_name2", o_string, &ippool_pool_name2,
	  "IP pool name for allocating local addresses. Default: use ippool_name." }, 
	{ "ippool_server", o_string, &ippool_server,
	  "IP pool server name or IP address" },
	{ "ippool_debug", o_int, &ippool_debug,
	  "Ippool debug. Default: no debug.", 
	  OPT_PRIO },
	{ NULL }
};

static int ippool_addr_alloc(CLIENT *cl, char *pool_name, u_int32_t *addr)
{
	int result;
	struct ippool_api_addr_alloc_msg_data clnt_res;

	result = ippool_addr_alloc_1(pool_name, &clnt_res, cl);
	if (result != RPC_SUCCESS) {
		fatal("ippool: %s", clnt_sperror(cl, ippool_server));
	}
	if (clnt_res.result_code < 0) {
		if (ippool_debug) {
			warn("IP address allocation from pool %s failed: %s", 
			     pool_name, strerror(-clnt_res.result_code));
		}
		result = clnt_res.result_code;
		goto out;
	}

	*addr = clnt_res.addr.s_addr;

	if (ippool_debug) {
		dbglog("Allocated address %s from pool %s", inet_ntoa(clnt_res.addr.s_addr), pool_name);
	}
out:
	return result;
}

static void ippool_addr_free(CLIENT *cl, char *pool_name, u_int32_t addr)
{
	int result;
	int clnt_res;
	struct ippool_api_ip_addr free_addr;

	free_addr.s_addr = addr;
	result = ippool_addr_free_1(pool_name, free_addr, &clnt_res, cl);
	if (result != RPC_SUCCESS) {
		fatal("ippool: %s", clnt_sperror(cl, ippool_server));
	}
	if (clnt_res < 0) {
		if (ippool_debug) {
			warn("IP address %s free to pool %s failed: %s", 
			     inet_ntoa(free_addr), pool_name, strerror(-clnt_res));
		}
		goto out;
	}

	if (ippool_debug) {
		dbglog("Freed address %s to pool %s", inet_ntoa(free_addr), pool_name);
	}
out:
	return;
}

static void ippool_release_ip(void)
{
	CLIENT *cl;

	if ((ippool_addr[0].s_addr != 0) || (ippool_addr[1].s_addr != 0)) {
		cl = clnt_create(ippool_server, IPPOOL_PROG, IPPOOL_VERSION, "udp");
		if (cl == NULL) {
			fatal("ippool: %s", clnt_spcreateerror(ippool_server));
		}

		if (ippool_addr[0].s_addr != 0) {
			ippool_addr_free(cl, ippool_pool_name, ippool_addr[0].s_addr);
			ippool_addr[0].s_addr = 0;
		}
		if (ippool_addr[1].s_addr != 0) {
			ippool_addr_free(cl, ippool_pool_name2 ? ippool_pool_name2 : ippool_pool_name, ippool_addr[1].s_addr);
			ippool_addr[1].s_addr = 0;
		}

		clnt_destroy(cl);
	}
}

static void ippool_cleanup(void *arg, int val)
{
	if (ippool_debug) {
		dbglog("ippool: Exiting. Releasing any allocated IP addresses.");
	}
	ippool_release_ip();
}

/* Unfortunately this hook only allows direct access to choose
 * a remote address but we also want to obtain local addresses 
 * from address pools. We need direct access into ipcp_wantoptions[]
 * as a workaround. See call to hook in ipcp.c.
 */
static void ippool_choose_ip(u_int32_t *hisaddr)
{
	ipcp_options *wo = &ipcp_wantoptions[0];
	ipcp_options *go = &ipcp_gotoptions[0];
	ipcp_options *ao = &ipcp_allowoptions[0];
	ipcp_options *ho = &ipcp_hisoptions[0];
	CLIENT *cl;
	int result = 0;

	cl = clnt_create(ippool_server, IPPOOL_PROG, IPPOOL_VERSION, "udp");
	if (cl == NULL) {
		fatal("ippool: %s", clnt_spcreateerror(ippool_server));
	}

	/* Allocate local and remote IP addresses unless they're
	 * already specified.  In the local address case, this only
	 * works when the "noipdefault" option is specified to prevent
	 * pppd from trying to use a default IP address.
	 */
	if (wo->ouraddr == 0) {
		result = ippool_addr_alloc(cl, ippool_pool_name2 ? ippool_pool_name2 : ippool_pool_name, &ippool_addr[1].s_addr);
		if (result < 0) {
			goto out;
		}

		/* We must mess with internal ipcp data here. Another
		 * result parameter like hisaddr would be much
		 * cleaner.
		 */
		wo->ouraddr = ippool_addr[1].s_addr;
		wo->accept_local = 0;
		go->ouraddr = ippool_addr[1].s_addr;
		go->accept_local = 0;
	} else {
		if (ippool_debug) {
			info("Using explicit local address %s", ip_ntoa(go->ouraddr));
		}
	}

	if (wo->hisaddr == 0) {
		result = ippool_addr_alloc(cl, ippool_pool_name, &ippool_addr[0].s_addr);
		if (result < 0) {
			goto out;
		}
		*hisaddr = ippool_addr[0].s_addr;

	} else {
		if (ippool_debug) {
			info("Using explicit remote address %s", ip_ntoa(go->hisaddr));
		}
	}

out:
	if (result < 0) {
		if (ippool_addr[0].s_addr != 0) {
			ippool_addr_free(cl, ippool_pool_name, ippool_addr[0].s_addr);
			ippool_addr[0].s_addr = 0;
		}
		if (ippool_addr[1].s_addr != 0) {
			ippool_addr_free(cl, ippool_pool_name2 ? ippool_pool_name2 : ippool_pool_name, ippool_addr[1].s_addr);
			ippool_addr[1].s_addr = 0;
		}
	}

	clnt_destroy(cl);
}

static int ippool_allowed_address(u_int32_t addr)
{
	return 1;
}

void plugin_init(void)
{
#if defined(__linux__)
	extern int new_style_driver;	/* From sys-linux.c */
	if (!ppp_available() && !new_style_driver)
		fatal("Kernel doesn't support ppp_generic - "
		    "needed for Ippool");
#else
	fatal("No IP pool support on this OS");
#endif
	add_options(ippool_options);

	memset(&ippool_addr, 0, sizeof(ippool_addr));

	allowed_address_hook = ippool_allowed_address;

	ip_choose_hook = ippool_choose_ip;
	ip_down_hook = ippool_release_ip;

	/* brute force, just in case ip_down_hook doesn't get called */
	add_notifier(&exitnotify, ippool_cleanup, 0);
}

