#include <unistd.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <netinet/in.h>
#include <net/if.h>
#include <sys/types.h>
#include <sys/socket.h>
#include <sys/ioctl.h>

#include <linux/types.h>
#include <linux/if_ether.h>    // For ETH_ALEN

#include <linux/ppp_defs.h>
#include <linux/if_ppp.h>
#include <linux/if_pppox.h>
#include <linux/if_pppol2tp.h>

#include "testlib.h"

/* FIXME: should be in system's socket.h... */
#define SOL_PPPOL2TP	269

static int part_1(void)
{
  int server_sock, session_sock;
  int data;
  int result;
  size_t optlen;

  /* Part 1: tunnel getsockopt/setsockopt */

  server_sock = OpenUDPSocket( 1701 );
  session_sock = OpenPPPoL2TPSocket();

  ConnectSock( session_sock, server_sock, 1701, 100, 0, 101, 0 );

  system( "./subtest-proc" );

  printf("tunnel getsockopt/setsockopt...\n");
  data = -1;
  result = setsockopt(session_sock, SOL_PPPOL2TP, PPPOL2TP_SO_DEBUG, &data, sizeof(data));
  if (result < 0) {
	  goto out;
  }
  system( "./subtest-proc" );

  optlen = sizeof(data);
  result = getsockopt(session_sock, SOL_PPPOL2TP, PPPOL2TP_SO_DEBUG, &data, &optlen);
  if (result < 0) {
	  goto out;
  }
  printf("SO_DEBUG=%d\n", data);
  
out:
  close( server_sock );
  close( session_sock );

  sleep(1);
  system( "./subtest-proc" );

  return result;
}

static int part_2(void)
{
  int server_sock, session_sock;
  int data;
  int result;
  size_t optlen;

  server_sock = OpenUDPSocket( 1701 );
  session_sock = OpenPPPoL2TPSocket();

  ConnectSock( session_sock, server_sock, 1701, 1, 2, 3, 4 );

  system( "./subtest-proc" );

  /* Part 2: session socket options */
  printf("session getsockopt/setsockopt...\n");
  data = 1;
  result = setsockopt(session_sock, SOL_PPPOL2TP, PPPOL2TP_SO_RECVSEQ, &data, sizeof(data));
  if (result < 0) {
	  goto out;
  }
  system( "./subtest-proc" );
  optlen = sizeof(data);
  result = getsockopt(session_sock, SOL_PPPOL2TP, PPPOL2TP_SO_RECVSEQ, &data, &optlen);
  if (result < 0) {
	  goto out;
  }
  printf("SO_RECVSEQ=%d\n", data);

  data = 1;
  result = setsockopt(session_sock, SOL_PPPOL2TP, PPPOL2TP_SO_SENDSEQ, &data, sizeof(data));
  if (result < 0) {
	  goto out;
  }
  system( "./subtest-proc" );
  optlen = sizeof(data);
  result = getsockopt(session_sock, SOL_PPPOL2TP, PPPOL2TP_SO_SENDSEQ, &data, &optlen);
  if (result < 0) {
	  goto out;
  }
  printf("SO_SENDSEQ=%d\n", data);

  data = 1;
  result = setsockopt(session_sock, SOL_PPPOL2TP, PPPOL2TP_SO_LNSMODE, &data, sizeof(data));
  if (result < 0) {
	  goto out;
  }
  system( "./subtest-proc" );
  optlen = sizeof(data);
  result = getsockopt(session_sock, SOL_PPPOL2TP, PPPOL2TP_SO_LNSMODE, &data, &optlen);
  if (result < 0) {
	  goto out;
  }
  printf("SO_LNSMODE=%d\n", data);

  data = -1;
  result = setsockopt(session_sock, SOL_PPPOL2TP, PPPOL2TP_SO_DEBUG, &data, sizeof(data));
  if (result < 0) {
	  goto out;
  }
  system( "./subtest-proc" );
  optlen = sizeof(data);
  result = getsockopt(session_sock, SOL_PPPOL2TP, PPPOL2TP_SO_DEBUG, &data, &optlen);
  if (result < 0) {
	  goto out;
  }
  printf("SO_DEBUG=%d\n", data);
  
  data = 200;
  result = setsockopt(session_sock, SOL_PPPOL2TP, PPPOL2TP_SO_REORDERTO, &data, sizeof(data));
  if (result < 0) {
	  goto out;
  }
  system( "./subtest-proc" );
  optlen = sizeof(data);
  result = getsockopt(session_sock, SOL_PPPOL2TP, PPPOL2TP_SO_REORDERTO, &data, &optlen);
  if (result < 0) {
	  goto out;
  }
  printf("SO_REORDERTO=%d\n", data);

out:
  close( server_sock );
  close( session_sock );

  sleep(1);
  system( "./subtest-proc" );

  return result;
}

static int part_3(void)
{
  int server_sock, session_sock;
  int data;
  int result;
  struct pppol2tp_ioc_stats stats;

  /* Part 3: session ioctls */

  server_sock = OpenUDPSocket( 1701 );
  session_sock = OpenPPPoL2TPSocket();

  ConnectSock( session_sock, server_sock, 1701, 1, 2, 3, 4 );

  system( "./subtest-proc" );

  /* send valid ioctls */
  printf("ioctl reads...\n");
  result = ioctl(session_sock, PPPIOCGMRU, &data);
  if (result < 0) {
	  goto out;
  }
  printf("mru=%d\n", data);
  result = ioctl(session_sock, PPPIOCGFLAGS, &data);
  if (result < 0) {
	  goto out;
  }
  printf("flags=%d\n", data);
  memset(&stats, 0, sizeof(stats));
  result = ioctl(session_sock, PPPIOCGL2TPSTATS, &stats);
  if (result < 0) {
	  goto out;
  }
  printf("stats=%llu %llu %llu %llu %llu %llu %llu %llu\n", 
	 stats.tx_packets, stats.tx_bytes, stats.tx_errors,
	 stats.rx_packets, stats.rx_bytes, stats.rx_errors,
	 stats.rx_seq_discards, stats.rx_oos_packets);

  printf("ioctl writes...\n");
  data = 1400;
  result = ioctl(session_sock, PPPIOCSMRU, &data);
  if (result < 0) {
	  goto out;
  }
  system( "./subtest-proc" );
  data = 1;
  result = ioctl(session_sock, PPPIOCSFLAGS, &data);
  if (result < 0) {
	  goto out;
  }
  system( "./subtest-proc" );

out:
  close( server_sock );
  close( session_sock );

  sleep(1);
  system( "./subtest-proc" );

  return result;
}

int main(int argc, char **argv)
{

  if (argc > 1) TestInit(0);

  part_1();
  part_2();
  part_3();
  
  return 0;
}
