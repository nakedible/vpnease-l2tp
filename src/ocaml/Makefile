all:
	ocamlfind ocamlopt -ccopt -static -package unix -linkpkg dhclient_signal.ml
	mv a.out dhclient_signal
	strip dhclient_signal
.PHONY: all

clean:
	rm -f dhclient_signal
