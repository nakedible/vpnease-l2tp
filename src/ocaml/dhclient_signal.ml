  (* Sends a signal based on first argument ("SIGUSR1"|"SIGUSR2"|"SIGHUP")
   * to the process whose pid is found in
   * /var/run/l2tpgw/l2tpgw-runner.pid if any. *)

exception InvalidArgument;;

let send_signal signal =
  let buf = Scanf.Scanning.from_file "/var/run/l2tpgw/l2tpgw-runner.pid" in
  let kill pid = Unix.handle_unix_error Unix.kill pid signal in
  Scanf.bscanf buf (format_of_string "%d") kill; 0;;

let action = Sys.argv.(1) in
match action with
| "SIGUSR1" -> send_signal Sys.sigusr1;
| "SIGUSR2" -> send_signal Sys.sigusr2;
| "SIGHUP" -> send_signal Sys.sighup;
| _ -> raise InvalidArgument;
