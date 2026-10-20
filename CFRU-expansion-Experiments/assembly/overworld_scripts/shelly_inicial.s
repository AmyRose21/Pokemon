@ ================================================================
@ SHELLY MODULE v1.4 - EventScript_ShellyArrival
@ Shelly llega por PC a tu cuarto en la primera partida nueva.
@
@ Disparado desde src/shelly_module.c (ShellyTryArrival) al entrar por
@ primera vez al CUARTO DEL JUGADOR (grupo 4, mapa 1) con el flag 0x2AE
@ sin fijar. Corre en el contexto GLOBAL del motor (SetupScript), el
@ mismo mecanismo vanilla de las escenas de Oak en Pallet: seguro para
@ mensajes con espera (waitmsg/waitfanfare/waitbuttonpress).
@
@ El texto gText_ShellyArrival vive en strings/Scripts/shelly_inicial.string
@ ================================================================
.align 2
.thumb

.include "../xse_commands.s"
.include "../xse_defines.s"
.include "../asm_defines.s"

@ MUS_OBTAIN_ITEM (258) del juego base: fanfarria de objeto recibido.
.equ MUS_OBTAIN_ITEM, 0x102

.global EventScript_ShellyArrival
EventScript_ShellyArrival:
	givepokemon SPECIES_SHELLY 5 ITEM_NONE 0 0 0
	lockall
	fanfare MUS_OBTAIN_ITEM
	preparemsg gText_ShellyArrival
	waitmsg
	waitfanfare
	waitbuttonpress
	closeonkeypress
	releaseall
	end
