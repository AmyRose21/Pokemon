// ================================================================
// SHELLY MODULE v1.4 - inicial de Shelly COMPILADA DENTRO DE LA ROM.
// (antes: parche_inicial.py aplicado sobre la ROM final; ya no existe)
//
// La primera vez que entras a TU CUARTO (grupo 4, mapa 1 = Casa del
// Jugador 2F de Pallet) con el flag 0x2AE sin fijar, Shelly llega:
// givepokemon nv.5 con fanfarria y mensaje en espanol.
//
// Se invoca desde TryRunOnFrameMapScript (src/overworld.c), el mismo
// mecanismo vanilla que las escenas de Oak en Pallet: el script corre
// en el contexto GLOBAL del motor, asi que los comandos de espera
// (waitmsg / waitfanfare / waitbuttonpress) son seguros aqui.
// ================================================================
#include "defines.h"
#include "../include/script.h"

// Flag vanilla SIN USO en FireRed US 1.0 (validado contra el decomp),
// dentro del rango seguro [0x1, 0x900). Las flags propias de la CFRU
// (NUZLOCKE etc.) viven en 0x900+, asi que no se pisan con nadie.
#define SHELLY_FLAG_INICIAL 0x2AE

// El evento de llegada vive en assembly/overworld_scripts/shelly_inicial.s
// y su texto en strings/Scripts/shelly_inicial.string.
extern const u8 EventScript_ShellyArrival[];

// TRUE si acaba de lanzar el evento de llegada (el llamador debe
// detenerse ese frame, igual que con los level scripts ON_FRAME).
bool8 ShellyTryArrival(void)
{
	// Reproduccion del quest-log (2=PLAYBACK, 3=PLAYBACK_LAST):
	// no entregar ni gastar el flag durante la repeticion.
	if (gQuestLogMode == 2 || gQuestLogMode == 3)
		return FALSE;

	// Estamos en el CUARTO DEL JUGADOR? Grupo 4 = IndoorPallet:
	// [0]=1F, [1]=2F del jugador, [2]=casa del rival, [3]=laboratorio.
	if (gSaveBlock1->location.mapGroup == 4
	 && gSaveBlock1->location.mapNum == 1)
	{
		if (!FlagGet(SHELLY_FLAG_INICIAL))
		{
			FlagSet(SHELLY_FLAG_INICIAL);
			ScriptContext1_SetupScript(EventScript_ShellyArrival);
			return TRUE;
		}
	}

	return FALSE;
}
