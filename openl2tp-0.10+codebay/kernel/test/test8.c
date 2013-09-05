#include <unistd.h>
#include <stdio.h>
#include <fcntl.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <netinet/in.h>
#include <net/if.h>
#include <stdlib.h>
#include <linux/if_ether.h>    // For ETH_ALEN

#include <linux/if_pppox.h>
#include <linux/if_pppol2tp.h>

#include "testlib.h"

int main(int argc, char **argv)
{
  int server_sock1, session_sock1;
  int server_sock2, session_sock2;
  
  if (argc > 1) TestInit(0);

  server_sock1 = OpenUDPSocket( 1701 );
  session_sock1 = OpenPPPoL2TPSocket();

  server_sock2 = OpenUDPSocket( 1702 );
  session_sock2 = OpenPPPoL2TPSocket();

  fcntl( server_sock1,  F_SETFD, FD_CLOEXEC );
  fcntl( session_sock1, F_SETFD, FD_CLOEXEC );
  fcntl( server_sock2,  F_SETFD, FD_CLOEXEC );
  fcntl( session_sock2, F_SETFD, FD_CLOEXEC );
  
  ConnectSock( session_sock1, server_sock1, 1702, 1, 2, 3, 4 );
  ConnectSock( session_sock2, server_sock2, 1701, 3, 4, 1, 2 );

  system( "./subtest-proc" );
  
  StartPPPDaemon( session_sock1, 1 );
  sleep(1);
  StartPPPDaemon( session_sock2, 0 );
  
  if (argc <= 1)
  {
    char buf[16];
    fprintf( stderr, "Press any key to continue\n" );
    fgets( buf, 10, stdin );
  }
  else
  {
    sleep(60);
  }
  system( "ifconfig ppp0" );
  system( "ifconfig ppp1" );

  system( "./subtest-proc" );

  /* Test that the kernel handles closing server/session sockets in
   * different orders.
   */
  TestPrintf( "Closing server2 socket\n" );  
  close( server_sock2 );
  TestPrintf( "Closing session2 socket\n" );  
  close( session_sock2 );
  TestPrintf( "Closing session1 socket\n" );  
  close( session_sock1 );
  TestPrintf( "Closing server1 socket\n" );  
  close( server_sock1 );

  sleep(4);
  system( "./subtest-proc" );

  /* This is a complete hack.... We don't keep track of our kids */
  TestPrintf( "Killing pppd processes\n" );  
  system( "killall pppd" );
  waitpid(0, NULL, 0);
  sleep(5);

  return 0;
}
