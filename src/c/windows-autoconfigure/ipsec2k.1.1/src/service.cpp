#include "service.h"

x4_service::x4_service()
{
  hManager = hService = 0;
}

x4_service::~x4_service()
{
  close();
}

bool x4_service::open(const char * name, DWORD sam)
{
  close();

  hManager = OpenSCManager(0,0,SC_MANAGER_ALL_ACCESS);
  hService = hManager ? OpenService(hManager, name, sam) : 0;

  if (! hService || ! hManager)
  {
    close();
    return false;
  }

  return true;
}

void x4_service::close()
{
  if (hService)
    CloseServiceHandle(hService);

  if (hManager)
    CloseServiceHandle(hManager);

  hManager = hService = 0;
}

bool x4_service::get_state(uint32 & state)
{
  SERVICE_STATUS st;
  
  assert(hService);

  if (! QueryServiceStatus(hService, &st))
    return false;

  state = st.dwCurrentState; 
  return true;
}

bool x4_service::start(int argc, const char ** argv)
{
  assert(hService);
  return StartService(hService, argc, argv) != 0;
}

bool x4_service::stop()
{
  return control(SERVICE_CONTROL_STOP);
}

bool x4_service::control(uint32 op_code)
{
  SERVICE_STATUS stTemp;

  assert(hService);
  return ControlService(hService, op_code, &stTemp) != 0;
}
