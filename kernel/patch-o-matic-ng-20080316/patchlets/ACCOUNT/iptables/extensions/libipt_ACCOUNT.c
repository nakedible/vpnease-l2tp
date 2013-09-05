/* Shared library add-on to iptables to add ACCOUNT(ing) support.
   Author: Intra2net AG <opensource@intra2net.com>
*/

#include <stdio.h>
#include <netdb.h>
#include <string.h>
#include <stdlib.h>
#include <syslog.h>
#include <getopt.h>
#include <iptables.h>
#include <linux/netfilter_ipv4/ip_tables.h>
#include <linux/netfilter_ipv4/ipt_ACCOUNT.h>

static struct option opts[] = {
    { .name = "addr",        .has_arg = 1, .flag = 0, .val = 'a' },
    { .name = "tname",       .has_arg = 1, .flag = 0, .val = 't' },
    { .name = 0 }
};

/* Function which prints out usage message. */
static void help(void)
{
    printf(
"ACCOUNT v%s options:\n"
" --%s ip/netmask\t\tBase network IP and netmask used for this table\n"
" --%s name\t\t\tTable name for the userspace library\n",
IPTABLES_VERSION, opts[0].name, opts[1].name);
}

/* Initialize the target. */
static void
init(struct ipt_entry_target *t, unsigned int *nfcache)
{
    struct ipt_acc_info *accountinfo = (struct ipt_acc_info *)t->data;

    accountinfo->table_nr = -1;

    /* Can't cache this */
    *nfcache |= NFC_UNKNOWN;
}

#define IPT_ACCOUNT_OPT_ADDR 0x01
#define IPT_ACCOUNT_OPT_TABLE 0x02

/* Function which parses command options; returns true if it
   ate an option */
static int
parse(int c, char **argv, int invert, unsigned int *flags,
      const struct ipt_entry *entry,
      struct ipt_entry_target **target)
{
    struct ipt_acc_info *accountinfo = (struct ipt_acc_info *)(*target)->data;
    struct in_addr *addrs = NULL, mask;
    unsigned int naddrs = 0;

    switch (c) {
    case 'a':
        if (*flags & IPT_ACCOUNT_OPT_ADDR)
                exit_error(PARAMETER_PROBLEM, "Can't specify --%s twice",
                            opts[0].name);

        if (check_inverse(optarg, &invert, NULL, 0))
                exit_error(PARAMETER_PROBLEM, "Unexpected `!' after --%s",
                            opts[0].name);

        //loginfo->level = parse_level(optarg);
        parse_hostnetworkmask(optarg, &addrs, &mask, &naddrs);
        
        if (naddrs > 1)
                exit_error(PARAMETER_PROBLEM, "multiple IP addresses not allowed");
        
        accountinfo->net_ip = addrs[0].s_addr;
        accountinfo->net_mask = mask.s_addr;
                
        *flags |= IPT_ACCOUNT_OPT_ADDR;
        break;

    case 't':
            if (*flags & IPT_ACCOUNT_OPT_TABLE)
                    exit_error(PARAMETER_PROBLEM,
                                "Can't specify --%s twice", opts[1].name);

            if (check_inverse(optarg, &invert, NULL, 0))
                    exit_error(PARAMETER_PROBLEM,
                                "Unexpected `!' after --%s", opts[1].name);

            if (strlen(optarg) > ACCOUNT_TABLE_NAME_LEN - 1)
                    exit_error(PARAMETER_PROBLEM,
                                "Maximum table name length %u for --%s",
                                ACCOUNT_TABLE_NAME_LEN - 1, opts[1].name);

            strcpy(accountinfo->table_name, optarg);
            *flags |= IPT_ACCOUNT_OPT_TABLE;
            break;
    
    default:
            return 0;
    }
    return 1;
}

/* Final check; nothing. */
static void final_check(unsigned int flags)
{
    if (!(flags&IPT_ACCOUNT_OPT_ADDR) || !(flags&IPT_ACCOUNT_OPT_TABLE))
        exit_error(PARAMETER_PROBLEM, "ACCOUNT: needs --%s and --%s",
                    opts[0].name, opts[1].name);
}

static void print_it(const struct ipt_ip *ip,
                     const struct ipt_entry_target *target, char do_prefix)
{
    const struct ipt_acc_info *accountinfo
        = (const struct ipt_acc_info *)target->data;
    struct in_addr a;

    if (!do_prefix)
        printf("ACCOUNT ");
    
    // Network information
    if (do_prefix)
	printf("--");
    printf("%s ", opts[0].name);
    
    a.s_addr = accountinfo->net_ip;	
    printf("%s", addr_to_dotted(&a));
    a.s_addr = accountinfo->net_mask;
    printf("%s", mask_to_dotted(&a));

    printf(" ");
    if (do_prefix)
	printf("--");

    printf("%s %s", opts[1].name, accountinfo->table_name);
}

/* Prints out the targinfo. */
static void
print(const struct ipt_ip *ip,
      const struct ipt_entry_target *target,
      int numeric)
{
    print_it (ip, target, 0);
}

/* Saves the union ipt_targinfo in parsable form to stdout. */
static void
save(const struct ipt_ip *ip, const struct ipt_entry_target *target)
{
    print_it(ip, target, 1);
}

static
struct iptables_target account
= {
    .next          = NULL,
    .name          = "ACCOUNT",
    .version       = IPTABLES_VERSION,
    .size          = IPT_ALIGN(sizeof(struct ipt_acc_info)),
    .userspacesize = IPT_ALIGN(sizeof(struct ipt_acc_info)),
    .help          = &help,
    .init          = &init,
    .parse         = &parse,
    .final_check   = &final_check,
    .print         = &print,
    .save          = &save,
    .extra_opts    = opts
};

void _init(void)
{
    register_target(&account);
}
