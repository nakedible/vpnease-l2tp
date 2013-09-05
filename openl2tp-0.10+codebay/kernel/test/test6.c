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

int main(int argc, char **argv)
{
  int server_sock1, session_sock1;
  int server_sock2, session_sock2;
  
  if (argc > 1) TestInit(0);

  server_sock1 = OpenUDPSocket( 1701 );
  session_sock1 = OpenPPPoL2TPSocket();

  server_sock2 = OpenUDPSocket( 1702 );
  session_sock2 = OpenPPPoL2TPSocket();

  /* Try sending packets first to see if that helps */
  SendTestPacket( server_sock1, 1702 );
  SendTestPacket( server_sock2, 1701 );

  fcntl( server_sock1,  F_SETFL, O_NONBLOCK );
  fcntl( session_sock1, F_SETFL, O_NONBLOCK );
  fcntl( server_sock2,  F_SETFL, O_NONBLOCK );
  fcntl( session_sock2, F_SETFL, O_NONBLOCK );

  CheckPipe( server_sock1 );
  CheckPipe( server_sock2 );
    
  ConnectSock( session_sock1, server_sock1, 1702, 1, 2, 3, 4 );
  ConnectSock( session_sock2, server_sock2, 1701, 3, 4, 1, 2 );

  system( "./subtest-proc" );
  
  SendTestDataPacket( session_sock1 );
  SendTestDataPacket( session_sock2 );

  system( "./subtest-proc" );

  CheckPipe( server_sock1 );
  CheckPipe( session_sock1 );
  CheckPipe( server_sock2 );
  CheckPipe( session_sock2 );
  
  system( "./subtest-proc" );

  TestPrintf( "Closing server2 socket\n" );  
  close( server_sock2 );
  TestPrintf( "Closing session2 socket\n" );  
  close( session_sock2 );
  TestPrintf( "Closing session1 socket\n" );  
  close( session_sock1 );
  TestPrintf( "Closing server1 socket\n" );  
  close( server_sock1 );
  
  return 0;
}
