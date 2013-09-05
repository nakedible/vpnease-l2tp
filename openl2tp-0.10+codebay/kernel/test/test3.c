#include <unistd.h>

#include <netinet/in.h>
#include <net/if.h>

#include <linux/if_ether.h>    // For ETH_ALEN

#include <linux/if_pppox.h>
#include <linux/if_pppol2tp.h>

#include "testlib.h"

int main(int argc, char **argv)
{
  int server_sock, session_sock;
  
  if (argc > 1) TestInit(0);

  server_sock = OpenUDPSocket( 1701 );
  session_sock = OpenPPPoL2TPSocket();
  
  close( server_sock );
  close( session_sock );
  
  return 0;
}
