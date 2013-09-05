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

char control_packet[] = "\x80\x02XXXXXXXXXXXX";  /* The first bit indicates control packet */
char data_packet[] = "\x02\x02\x00\x01\x00\x02\x00\x00""ABCDEFG";  /* Data with offset bit */

int main(int argc, char **argv)
{
  int server_sock, session_sock;
  
  if (argc > 1) TestInit(0);

  server_sock = OpenUDPSocket( 1701 );
  session_sock = OpenPPPoL2TPSocket();

  /* Try sending packets first to see if that helps */
  // SendRawPacket( server_sock, 1701, control_packet, sizeof( control_packet ) );
  // SendRawPacket( server_sock, 1701, data_packet,    sizeof( data_packet    ) );

  fcntl( server_sock, F_SETFL, O_NONBLOCK );
  fcntl( session_sock, F_SETFL, O_NONBLOCK );
  
  CheckPipe( server_sock );
  
  ConnectSock( session_sock, server_sock, 1701, 1, 2, 3, 4 );

  system( "./subtest-proc" );
  
  SendRawPacket( server_sock, 1701, control_packet, sizeof( control_packet ) );
  SendRawPacket( server_sock, 1701, data_packet,    sizeof( data_packet    ) );

  system( "./subtest-proc" );

  CheckPipe( server_sock );
  CheckPipe( session_sock );

  system( "./subtest-proc" );
  
  /* Close session socket first, because other way round breaks right now */  
  TestPrintf( "Closing session socket\n" );  
  close( session_sock );
  TestPrintf( "Closing server socket\n" );  
  close( server_sock );
  
  return 0;
}
