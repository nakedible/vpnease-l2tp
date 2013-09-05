#include <unistd.h>
#include <stdio.h>
#include <fcntl.h>
#include <netinet/in.h>
#include <net/if.h>
#include <stdlib.h>
#include <linux/if_ether.h>    // For ETH_ALEN

#include <linux/if_pppox.h>
#include <linux/if_pppol2tp.h>

#include "testlib.h"

#define NUM_SESSIONS 1000

int main(int argc, char **argv)
{
  int server_sock, session_sock[NUM_SESSIONS];
  int i;
  int result;

  if (argc > 1) TestInit(0);

  result = sysconf(_SC_OPEN_MAX);
  if (result < 0) {
	  fprintf(stderr, "sysconf(): %m");
	  exit(result);
  }
  if (result < (NUM_SESSIONS + 10)) {
	  fprintf(stderr, "System OPEN_MAX is too small. See ulimit -n\n");
	  exit(1);
  }

  server_sock = OpenUDPSocket( 1701 );
  fcntl( server_sock,  F_SETFL, O_NONBLOCK );
  fcntl( server_sock,  F_SETFD, FD_CLOEXEC );

  for (i = 0; i < NUM_SESSIONS; i++) {
	  session_sock[i] = OpenPPPoL2TPSocket();
	  fcntl( session_sock[i], F_SETFL, O_NONBLOCK );
	  fcntl( session_sock[i], F_SETFD, FD_CLOEXEC );
	  ConnectSock( session_sock[i], server_sock, 1701, 10000+i, 20000+i, 30000+i, 40000+i );
  }


  system( "./subtest-proc" );
    
  if (argc <= 1) {
    char buf[16];
    fprintf( stderr, "Press any key to continue\n" );
    fgets( buf, 10, stdin );
  } else {
    sleep(60);
  }

  TestPrintf( "Closing server socket\n" );  
  close( server_sock );

  sleep(4);
  system( "./subtest-proc" );
  
  return 0;
}
