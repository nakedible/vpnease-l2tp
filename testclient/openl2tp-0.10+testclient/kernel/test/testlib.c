#include <unistd.h>
#include <stdlib.h>
#include <stdarg.h>
#include <stdio.h>
#include <errno.h>
#include <sys/socket.h>
#include <string.h>
#include <stdlib.h>
#include <netinet/in.h>
#include <net/if.h>
#include <time.h>
#include <linux/if_ether.h>    // For ETH_ALEN
#include <fcntl.h>

#include <linux/if_pppox.h>
#include <linux/if_pppol2tp.h>

#include "testlib.h"

static int TestVerbose = 1;

void TestInit( int verbose )
{
  TestVerbose = verbose;
}

int TestPrintf( const char *fmt, ... )
{
  int len;
  va_list args;
  va_start(args, fmt);

  if (TestVerbose == 0)
  {
    return 0;
  }

  len = vprintf(fmt, args);
  va_end(args);

  return len;
}

int OpenUDPSocket( int port )
{
  struct sockaddr_in sin;
  
  TestPrintf( "Opening UDP socket\n" );
  int fd = socket( AF_INET, SOCK_DGRAM, 0 );
  if( fd < 0 )
  {
    TestPrintf( "Open failed: %s\n", strerror( errno ) );
    exit(1);
  }

  memset(&sin, 0, sizeof(sin));
  sin.sin_addr.s_addr = 0;
  sin.sin_port = htons( port );
  sin.sin_family = AF_INET;
  
  if( bind( fd, (struct sockaddr*)&sin, sizeof(sin) ) )
  {
    TestPrintf( "Bind failed: %s\n", strerror( errno ) );
    exit(1);
  }
  return fd;
}

int OpenPPPoL2TPSocket()
{
  TestPrintf( "Opening PPPoL2TP socket\n" );
  int fd = socket( AF_PPPOX, SOCK_DGRAM, PX_PROTO_OL2TP );
  if( fd < 0 )
  {
    TestPrintf( "Open failed: %s\n", strerror( errno ) );
    exit(1);
  }
  return fd;
}

int ConnectSock( int sock, int serversock, int port, int t1, int s1, int t2, int s2 )
{
  struct sockaddr_pppox sax;
  int on = 1;

  TestPrintf( "Connecting socket\n" );

  /* Note, the target socket must be bound already, else it will not be ready */  
  memset(&sax, 0, sizeof(sax));
  sax.sa_family = AF_PPPOX;
  sax.sa_protocol = PX_PROTO_OL2TP;
  sax.sa_addr.pppol2tp.fd = serversock;
  sax.sa_addr.pppol2tp.addr.sin_addr.s_addr = htonl( 0x7F000001 );
  sax.sa_addr.pppol2tp.addr.sin_port        = htons( port );
  sax.sa_addr.pppol2tp.addr.sin_family      = AF_INET;
  sax.sa_addr.pppol2tp.s_tunnel  = t1;
  sax.sa_addr.pppol2tp.s_session = s1;
  sax.sa_addr.pppol2tp.d_tunnel  = t2;
  sax.sa_addr.pppol2tp.d_session = s2;
  
  if( connect( sock, (struct sockaddr *)&sax, sizeof(sax) ) < 0 )
  {
    TestPrintf( "Connect failed: %s\n", strerror( errno ) );
  }

  (void) setsockopt(sock, SOL_SOCKET, SO_NO_CHECK, (char *)&on, sizeof(on));

  return 0;
}

/* Send raw data packet to loopback */
int SendRawPacket( int fd, int port, void *data, int len )
{
  struct sockaddr_in sin;
  
  TestPrintf( "Sending %d bytes of data to fd %d\n", len, fd );
  memset(&sin, 0, sizeof(sin));
  sin.sin_family = AF_INET;
  sin.sin_port = htons( port );
  sin.sin_addr.s_addr = htonl( 0x7f000001 );
  
  if( sendto( fd, data, len, 0, (struct sockaddr*)&sin, sizeof(sin) ) < 0 )
  {
    TestPrintf( "SendTo failed: %s\n", strerror( errno ) );
    exit(1);
  }
  return 0;
}

#define PKT_MAGIC 0x89374FF3

struct TestPacket
{
  char header[2];
  int magic;
  int id;
};

static int PacketID = 1;

void CheckPipe( int fd )
{
  int len;
  TestPrintf( "Checking fd %d\n", fd );
  {
    char buffer[100];
    while( (len = read( fd, buffer, 100 )) > 0 )
    {
      if( len == sizeof(struct TestPacket) && ((struct TestPacket*)buffer)->magic == PKT_MAGIC )
      {
        TestPrintf( "Received packet: len=%d (ID=%d)\n", len, ((struct TestPacket*)buffer)->id );
      }
      else
      {
        TestPrintf( "Received packet: len=%d\n", len );
      }
    }
  }
} 

void SendTestPacket( int fd, int port )
{
  struct sockaddr_in sin;
  
  struct TestPacket pkt;
  pkt.header[ 0] = 0x80;
  pkt.header[ 1] = 0x02;
  pkt.magic = PKT_MAGIC;
  pkt.id = PacketID++;

  TestPrintf( "Sending  test packet to fd %d (ID=%d)\n", fd, pkt.id );
  memset(&sin, 0, sizeof(sin));
  sin.sin_family = AF_INET;
  sin.sin_port = htons( port );
  sin.sin_addr.s_addr = htonl( 0x7f000001 );
  
  if( sendto( fd, &pkt, sizeof(pkt), MSG_DONTWAIT, (struct sockaddr*)&sin, sizeof(sin) ) < 0 )
  {
    TestPrintf( "SendTo failed: %s\n", strerror( errno ) );
    exit(1);
  }
  return;
}

void SendTestDataPacket( int fd )
{
  struct TestPacket pkt;
  pkt.header[ 0] = 0x80;
  pkt.header[ 1] = 0x02;
  pkt.magic = PKT_MAGIC;
  pkt.id = PacketID++;

  TestPrintf( "Sending  test data packet to fd %d (ID=%d)\n", fd, pkt.id );
  
  if( send( fd, &pkt, sizeof(pkt), MSG_DONTWAIT ) < 0 )
  {
    TestPrintf( "Send failed: %s\n", strerror( errno ) );
    exit(1);
  }
  return;
}

void StartPPPDaemon( int fd, int server )
{
  static int ipOctet = 1;

  TestPrintf( "Spawning PPPD on fd %d\n", fd );
  if( fork() == 0 )
  {
    char address[32];
    char arg[8];
    
    fcntl( fd,  F_SETFD, 0 );   // Remove close on exec flag
    
    if (server) 
    {
      sprintf( address, "10.0.0.%d:10.0.0.%d", ipOctet, ipOctet + 1 );
      ipOctet += 2;
    }
    sprintf( arg, "%d", fd );
    
    if (server) 
    {
      execl( "/usr/sbin/pppd", "pppd", "debug", "noauth", 
	     address, "passive",
	     "mtu", "1460", "mru", "1460",
	     "plugin", "pppol2tp.so", "pppol2tp", arg,                         // PPPoX support
	     NULL );
    }
    else
    {
      execl( "/usr/sbin/pppd", "pppd", "debug", "noauth", 
	     "noipdefault",  "ipcp-accept-local", "ipcp-accept-remote",
	     "mtu", "1460", "mru", "1460",
	     "plugin", "pppol2tp.so", "pppol2tp", arg,                         // PPPoX support
	     NULL );
    }
    
    TestPrintf( "Exec failed: %s\n", strerror(errno) );
    exit(0);
  }
}

void StartLoopingFunction( int fd, int port, int id )
{
  int pid = id;

  TestPrintf( "Spawning looper on fd %d\n", fd );
  if( fork() != 0 )
    return;

  if (id == 0)
  {
    PacketID = ( getpid() - getppid() ) * 256;
    pid = getpid();
  }
  else
  {
    PacketID = id;
  }

  {
    int i, j;
    
    for( i=0; i<10; i++ )
    {
      TestPrintf( "[%d]: ", pid );
      SendTestPacket( fd, port );
      
      for( j=0; j<10; j++ )
      {
        char buffer[100];
        struct timespec spec;
        int len;
        
        while( (len = read( fd, buffer, 100 )) > 0 )
        {
          if( len == sizeof(struct TestPacket) && ((struct TestPacket*)buffer)->magic == PKT_MAGIC )
          {
            TestPrintf( "[%d]: Received test packet on fd %d (ID=%d)\n", pid, fd, ((struct TestPacket*)buffer)->id );
          }
          else
          {
            TestPrintf( "[%d]: Received packet: len=%d\n", pid, len );
          }
        }
        spec.tv_sec = 0;
        spec.tv_nsec = 100000000;
        nanosleep( &spec, NULL );
      }
    }
  }
  exit(0);
}

