#pragma once

#include "../global.h"
#include "../pokemon.h"

/**
 * \file ability_battle_effects.h
 * \brief Contains functions relating to the effects certain abilities have in battle.
 *		  Also includes the ability pop-up.
 */

//Exported Functions
u8 AbilityBattleEffects(u8 caseID, u8 bank, ability_t ability, ability_t special, u16 moveArg);
void AnimTask_LoadAbilityPopUp(u8 taskId);
void AnimTask_DestroyAbilityPopUp(u8 taskId);
void TransferAbilityPopUpHelper(void);
void TransferAbilityPopUpHelperAsTrace(void);
void TransferAbilityPopUpHelperAsImposter(void);
void TransferAbilityPopUp(u8 bank, ability_t ability);
u16 GetHighestStat(u8 bankAtk);
u16 GetHighestStatMon(struct Pokemon* mon);
bool8 IsParadoxBoostActive(u8 bank);
u8 GetParadoxBoostedStat(u8 bank);

//Functions Hooked In
pokemon_t* UpdateNickForIllusion(pokemon_t* mon);
u8 UpdatePokeBallForIllusion(u8 bank);
species_t TryUpdateIllusionYDelta(u8 bank);
