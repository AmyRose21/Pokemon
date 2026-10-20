#include "defines.h"
#include "defines_battle.h"
#include "../include/string_util.h"
#include "../include/constants/abilities.h"
#include "../include/constants/pokedex.h"
#include "../include/constants/species.h"

#include "../include/new/ability_tables.h"
#include "../include/new/ability_util.h"
#include "../include/new/battle_util.h"
#include "../include/new/move_tables.h"
#include "../include/new/util.h"

extern const u8 gAbilityNames[][ABILITY_NAME_LENGTH + 1];
extern const u8* gAbilityDescriptions[];

const u8* GetAbilityName(ability_t ability, unusedArg const u16 species)
{
	if (ability >= ABILITIES_COUNT)
		ability = ABILITY_NONE;

	const u8* ptr = gAbilityNames[ability];

	if (ptr[3] == 0x8 || ptr[3] == 0x9) //Expanded Ability Names
		ptr = T1_READ_PTR(ptr);

	return ptr;
}

const u8* GetAbilityDescription(ability_t ability, unusedArg const u16 species)
{
	if (ability >= ABILITIES_COUNT)
		return gAbilityDescriptions[ABILITY_NONE];

	const u8* desc = gAbilityDescriptions[ability];
	return desc;
}

void CopyAbilityName(u8* dst, ability_t ability, const u16 species)
{
	StringCopy(dst, GetAbilityName(ability, species));
}

// FireRed's summary struct reserves exactly 13 bytes for this field.  Keep the
// full canonical name everywhere else, but always leave room for EOS here so a
// long name cannot run into abilityDescStrBuf.
void CopyAbilityNameForSummary(u8* dst, ability_t ability, const u16 species)
{
	const u8 *src = GetAbilityName(ability, species);
	u32 i;

	for (i = 0; i < 12 && src[i] != EOS; ++i)
		dst[i] = src[i];
	dst[i] = EOS;
}

void CopyAbilityDescription(u8* dst, ability_t ability, const u16 species)
{
	StringCopy(dst, GetAbilityDescription(ability, species));
}

u16 GetProperAbilityPopUpSpecies(u8 bank)
{
	if (gNewBS->tookAbilityFrom[bank] != SPECIES_NONE)
		return gNewBS->tookAbilityFrom[bank];
	else
		return SPECIES(bank);
}

void SetProperAbilityPopUpSpecies(u8 bank)
{
	gAbilityPopUpSpecies = GetProperAbilityPopUpSpecies(bank);
}

void SetTookAbilityFrom(u8 taker, u8 takenFrom)
{
	if (gNewBS->tookAbilityFrom[takenFrom] != SPECIES_NONE)
		gNewBS->tookAbilityFrom[taker] = gNewBS->tookAbilityFrom[takenFrom]; //Pass along species
	else
		gNewBS->tookAbilityFrom[taker] = SPECIES(takenFrom);
}

void SwapTookAbilityFrom(u8 bank1, u8 bank2)
{
	u16 species1 = GetProperAbilityPopUpSpecies(bank1);
	u16 species2 = GetProperAbilityPopUpSpecies(bank2);

	gNewBS->tookAbilityFrom[bank1] = species2;
	gNewBS->tookAbilityFrom[bank2] = species1;
}

void ResetTookAbilityFrom(u8 bank)
{
	gNewBS->tookAbilityFrom[bank] = SPECIES_NONE;
}

bool8 IsTargetAbilityIgnored(ability_t defAbility, ability_t atkAbility, u16 move)
{
	if (atkAbility == ABILITY_MYCELIUMMIGHT && SPLIT(move) == SPLIT_STATUS)
		return gSpecialAbilityFlags[defAbility].gMyceliumMighIgnoredAbilities;

	return IS_MOLD_BREAKER(atkAbility, move) && gSpecialAbilityFlags[defAbility].gMoldBreakerIgnoredAbilities;
}

bool8 IsTargetAbilityIgnoredNoMove(ability_t defAbility, ability_t atkAbility)
{
	return IsMoldBreakerAbility(atkAbility) && gSpecialAbilityFlags[defAbility].gMoldBreakerIgnoredAbilities;
}

bool8 SpeciesHasTurboblaze(unusedArg u16 species)
{
	#if (defined SPECIES_RESHIRAM && defined SPECIES_KYUREM_WHITE)
	return species == SPECIES_RESHIRAM
		|| species == SPECIES_KYUREM_WHITE;
	#else
	return FALSE;
	#endif
}

bool8 SpeciesHasTeravolt(unusedArg u16 species)
{
	#if (defined SPECIES_ZEKROM && defined SPECIES_KYUREM_BLACK)
	return species == SPECIES_ZEKROM
		|| species == SPECIES_KYUREM_BLACK;
	#else
	return FALSE;
	#endif
}

bool8 SpeciesHasDrillBeak(unusedArg u16 species) //Custom Unbound Ability
{
	#if (defined SPECIES_SPEAROW && defined SPECIES_FEAROW)
	return species == SPECIES_SPEAROW || species == SPECIES_FEAROW;
	#else
	return FALSE;
	#endif
}

bool8 SpeciesHasGrassDash(unusedArg u16 species) //Custom Unbound Ability
{
	#ifdef SPECIES_SUNFLORA
	return species == SPECIES_SUNFLORA;
	#else
	return FALSE;
	#endif
}

bool8 SpeciesHasEvaporate(unusedArg u16 species) //Custom Unbound Ability
{
	#ifdef SPECIES_MAGCARGO
	return species == SPECIES_MAGCARGO;
	#else
	return FALSE;
	#endif
}

bool8 SpeciesHasSlipperyTail(unusedArg u16 species) //Custom Unbound Ability
{
	#ifdef SPECIES_SEVIPER
	return species == SPECIES_SEVIPER;
	#else
	return FALSE;
	#endif
}

bool8 IsClearBodyAbility(ability_t ability)
{
	return ability == ABILITY_CLEARBODY
		#ifdef ABILITY_FULLMETALBODY
		|| ability == ABILITY_FULLMETALBODY
		#endif
		#ifdef ABILITY_WHITESMOKE
		|| ability == ABILITY_WHITESMOKE
		#endif
		;
}

bool8 IsMoldBreakerAbility(ability_t ability)
{
	return ability == ABILITY_MOLDBREAKER
		#ifdef ABILITY_TURBOBLAZE
		|| ability == ABILITY_TURBOBLAZE
		#endif
		#ifdef ABILITY_TERAVOLT
		|| ability == ABILITY_TERAVOLT
		#endif
		;
}

bool8 IsMoxieAbility(ability_t ability)
{
	switch (ability)
	{
		case ABILITY_MOXIE:
		#ifdef ABILITY_GRIMNEIGH
		case ABILITY_GRIMNEIGH:
		#endif
		#ifdef ABILITY_CHILLINGNEIGH
		case ABILITY_CHILLINGNEIGH:
		#endif
		#ifdef ABILITY_ASONESHADOWRIDER
		case ABILITY_ASONESHADOWRIDER:
		#endif
		#ifdef ABILITY_ASONEICERIDER
		case ABILITY_ASONEICERIDER:
		#endif
		case ABILITY_BEASTBOOST:
		case ABILITY_SOULHEART:
		case ABILITY_BATTLEBOND:
			return TRUE;
		default:
			return FALSE;
	}
}

bool8 IsChoiceAbility(ability_t ability)
{
	return ability == ABILITY_GORILLATACTICS;
}

bool8 IsHPAbsorptionAbility(ability_t ability)
{
	switch (ability)
	{
		case ABILITY_WATERABSORB:
		case ABILITY_VOLTABSORB:
			return TRUE;
		default:
			return FALSE;
	}
}

bool8 IsElectricAbsorptionAblity(ability_t ability)
{
	switch (ability)
	{
		case ABILITY_VOLTABSORB:
		case ABILITY_MOTORDRIVE:
		case ABILITY_LIGHTNINGROD:
			return TRUE;
		default:
			return FALSE;
	}
}

bool8 IsPlusMinusAbility(ability_t ability)
{
	if (SpeciesHasPoisonPuppeteer(LEECH_SPECIES(gActiveBattler)) || SpeciesHasMyceliumMight(LEECH_SPECIES(gActiveBattler)))
		return FALSE;

	switch (ability)
	{
		case ABILITY_PLUS:
		case ABILITY_MINUS:
			return TRUE;
		default:
			return FALSE;
	}
}

bool8 IsMultiscaleAbility(ability_t ability)
{
	switch (ability)
	{
		case ABILITY_MULTISCALE:
		case ABILITY_SHADOWSHIELD:
			return TRUE;
		default:
			return FALSE;
	}
}

bool8 IsPriorityBlockingAbility(ability_t ability)
{
	switch (ability)
	{
		case ABILITY_DAZZLING:
		#ifdef ABILITY_QUEENLYMAJESTY
		case ABILITY_QUEENLYMAJESTY:
		#endif
			return TRUE;
		default:
			return FALSE;
	}
}

bool8 IsUnnerveAbility(ability_t ability)
{
	return ability == ABILITY_UNNERVE
		#ifdef ABILITY_ASONESHADOWRIDER
		|| ability == ABILITY_ASONESHADOWRIDER
		#endif
		#ifdef ABILITY_ASONEICERIDER
		|| ability == ABILITY_ASONEICERIDER
		#endif
		;
}

bool8 UnnerveOnOpposingField(u8 bank)
{
	return ABILITY_ON_OPPOSING_FIELD(bank, ABILITY_UNNERVE)
		#ifdef ABILITY_ASONESHADOWRIDER
		|| ABILITY_ON_OPPOSING_FIELD(bank, ABILITY_ASONESHADOWRIDER)
		#endif
		#ifdef ABILITY_ASONEICERIDER
		|| ABILITY_ON_OPPOSING_FIELD(bank, ABILITY_ASONEICERIDER)
		#endif
		;
}

bool8 AbilityIncreasesWildItemChance(ability_t ability)
{
	return ability == ABILITY_COMPOUNDEYES || ability == ABILITY_SUPERLUCK;
}

bool8 AbilityBlocksIntimidate(ability_t ability)
{
	return ability == ABILITY_INNERFOCUS
		|| ability == ABILITY_OWNTEMPO
		|| ability == ABILITY_OBLIVIOUS
		|| ability == ABILITY_SCRAPPY;
}

bool8 AbilityPreventsLoweringAtk(ability_t ability)
{
	return ability == ABILITY_HYPERCUTTER
		|| ability == ABILITY_MIRRORARMOR
		|| IsClearBodyAbility(ability);
}

bool8 AbilityPreventsLoweringStat(ability_t ability, u8 statId)
{
	switch (ability)
	{
		case ABILITY_HYPERCUTTER:
			return statId == STAT_STAGE_ATK;
		case ABILITY_BIGPECKS:
			return statId == STAT_STAGE_DEF;
		case ABILITY_KEENEYE:
			return statId == STAT_STAGE_ACC;
		default:
			return FALSE;
	}
}

bool8 AbilityRaisesOneStatWhenSomeStatIsLowered(ability_t ability)
{
	return ability == ABILITY_DEFIANT
		|| ability == ABILITY_COMPETITIVE;
}

bool8 IsAffectedBySturdy(ability_t defAbility, u8 bankDef)
{
	return defAbility == ABILITY_STURDY
		&& BATTLER_MAX_HP(bankDef);
}

bool8 IsAffectedByDisguse(unusedArg ability_t defAbility, unusedArg u16 defSpecies, unusedArg u8 moveSplit)
{
	#ifdef SPECIES_MIMIKYU
	if (defAbility == ABILITY_DISGUISE && defSpecies == SPECIES_MIMIKYU)
		return TRUE;
	#endif
	#ifdef SPECIES_EISCUE
	if (defAbility == ABILITY_ICEFACE && defSpecies == SPECIES_EISCUE && moveSplit == SPLIT_PHYSICAL)
		return TRUE;
	#endif

	return FALSE;
}

bool8 IsAffectedByBadDreams(u8 bank)
{
	return BATTLER_ALIVE(bank)
		&& (gBattleMons[bank].status1 & STATUS_SLEEP
		 || ABILITY(FOE(bank)) == ABILITY_COMATOSE)
		&& ABILITY(bank) != ABILITY_MAGICGUARD;
}

bool8 IsTrappedByAbility(u8 bankDef, ability_t trapAbility)
{
	if (!CanBeTrapped(bankDef))
		return FALSE;

	switch (trapAbility)
	{
		case ABILITY_SHADOWTAG:
			return ABILITY(bankDef) != ABILITY_SHADOWTAG; //Shadow Tag's not affected by Shadow Tag
		case ABILITY_ARENATRAP:
			return CheckGrounding(bankDef) == GROUNDED;
		case ABILITY_MAGNETPULL:
			return IsOfType(bankDef, TYPE_STEEL);
		default:
			return FALSE;
	}
}

bool8 BankHasEvaporate(unusedArg u8 bank)
{
	return FALSE;
}

bool8 BankOnFieldHasEvaporate(void)
{
	for (u32 i = 0; i < gBattlersCount; ++i)
	{
		u8 bank = gBanksByTurnOrder[i];

		if (BATTLER_ALIVE(bank)
		&& BankHasEvaporate(bank)
		&& AffectedByRain(bank))
			return bank + 1;
	}

	return FALSE;
}

bool8 IsWhiteSmokeAbility(ability_t ability, unusedArg u16 species)
{
	return ability == ABILITY_WHITESMOKE;
}

bool8 IsVitalSpiritAbility(ability_t ability, unusedArg u16 species)
{
	return ability == ABILITY_VITALSPIRIT;
}

bool8 SpeciesHasAngerShell(unusedArg u16 species)
{
	#ifdef SPECIES_KLAWF
	return species == SPECIES_KLAWF;
	#else
	return FALSE;
	#endif
}

bool8 SpeciesHasArmorTail(unusedArg u16 species)
{
	#ifdef SPECIES_FARIGIRAF
	return species == SPECIES_FARIGIRAF;
	#else
	return FALSE;
	#endif
}

bool8 SpeciesHasBeadsofRuin(unusedArg u16 species)
{
	#ifdef SPECIES_CHI_YU
	return species == SPECIES_CHI_YU;
	#else
	return FALSE;
	#endif
}

bool8 SpeciesHasSwordofRuin(unusedArg u16 species)
{
	#ifdef SPECIES_CHIEN_PAO
	return species == SPECIES_CHIEN_PAO;
	#else
	return FALSE;
	#endif
}

bool8 SpeciesHasTabletsofRuin(unusedArg u16 species)
{
	#ifdef SPECIES_WO_CHIEN
	return species == SPECIES_WO_CHIEN;
	#else
	return FALSE;
	#endif
}

bool8 SpeciesHasVesselofRuin(unusedArg u16 species)
{
	#ifdef SPECIES_TING_LU
	return species == SPECIES_TING_LU;
	#else
	return FALSE;
	#endif
}

bool8 SpeciesHasCostar(unusedArg u16 species)
{
	#ifdef SPECIES_FLAMIGO
	return species == SPECIES_FLAMIGO;
	#else
	return FALSE;
	#endif
}

bool8 SpeciesHasEarthEater(unusedArg u16 species)
{
	#ifdef SPECIES_ORTHWORM
	return species == SPECIES_ORTHWORM;
	#else
	return FALSE;
	#endif
}

bool8 SpeciesHasElectromorphosis(unusedArg u16 species)
{
	#ifdef SPECIES_BELLIBOLT
	return species == SPECIES_BELLIBOLT;
	#else
	return FALSE;
	#endif
}

bool8 SpeciesHasCudChew(unusedArg u16 species)
{
	#if (defined SPECIES_TAUROS_P && SPECIES_TAUROS_AQUA_P && SPECIES_TAUROS_BLAZE_P && SPECIES_FARIGIRAF)
	return species == SPECIES_TAUROS_P || species == SPECIES_TAUROS_AQUA_P || species == SPECIES_TAUROS_BLAZE_P || species == SPECIES_FARIGIRAF;
	#else
	return FALSE;
	#endif
}

bool8 SpeciesHasGoodAsGold(unusedArg u16 species)
{
	#ifdef SPECIES_GHOLDENGO
	return species == SPECIES_GHOLDENGO;
	#else
	return FALSE;
	#endif
}

bool8 SpeciesHasGuardDog(unusedArg u16 species)
{
	#if(defined SPECIES_MABOSSTIFF && SPECIES_OKIDOGI)
	return species == SPECIES_MABOSSTIFF || species == SPECIES_OKIDOGI;
	#else
	return FALSE;
	#endif
}

bool8 GuardDogPreventsLoweringStat(ability_t ability, u8 statId, unusedArg u8 bank)
{
	return ability == ABILITY_GUARDDOG && statId == STAT_STAGE_ATK;
}

bool8 SpeciesHasHadronEngine(unusedArg u16 species)
{
	#ifdef SPECIES_MIRAIDON
	return species == SPECIES_MIRAIDON;
	#else
	return FALSE;
	#endif
}

bool8 SpeciesHasMindsEye(unusedArg u16 species)
{
	#ifdef SPECIES_URSALUNA_BLOODMOON
	return species == SPECIES_URSALUNA_BLOODMOON;
	#else
	return FALSE;
	#endif
}

bool8 MindsEyePreventsLoweringStat(ability_t ability, u8 statId)
{
	return ability == ABILITY_MINDSEYE && statId == STAT_STAGE_ACC;
}	

bool8 SpeciesHasMyceliumMight(unusedArg u16 species)
{
	#if (defined SPECIES_TOEDSCOOL && SPECIES_TOEDSCRUEL)
	return species == SPECIES_TOEDSCOOL || species == SPECIES_TOEDSCRUEL;
	#else
	return FALSE;
	#endif
}

bool8 SpeciesHasOportunist(unusedArg u16 species)
{
	#ifdef SPECIES_ESPATHRA
	return species == SPECIES_ESPATHRA;
	#else
	return FALSE;
	#endif
}

bool8 SpeciesHasOrichalcumPulse(unusedArg u16 species)
{
	#ifdef SPECIES_KORAIDON
	return species == SPECIES_KORAIDON;
	#else
	return FALSE;
	#endif
}

bool8 IsFullMetalBodyAbility(ability_t ability, unusedArg u16 species)
{
	return ability == ABILITY_FULLMETALBODY;
}

bool8 SpeciesHasProtosynthesis(unusedArg u16 species) //Custom Unbound Ability
{
	#if (defined SPECIES_GOUGING_FIRE && SPECIES_RAGING_BOLT && SPECIES_GREAT_TUSK && SPECIES_SCREAM_TAIL && SPECIES_BRUTE_BONNET && SPECIES_FLUTTER_MANE && SPECIES_SLITHER_WING && SPECIES_SANDY_SHOCKS && SPECIES_ROARING_MOON && SPECIES_WALKING_WAKE)
	return species == SPECIES_GOUGING_FIRE || species == SPECIES_RAGING_BOLT || species == SPECIES_GREAT_TUSK || species == SPECIES_SCREAM_TAIL || species == SPECIES_BRUTE_BONNET || species == SPECIES_FLUTTER_MANE || species == SPECIES_SLITHER_WING || species == SPECIES_SANDY_SHOCKS || species == SPECIES_ROARING_MOON || species == SPECIES_WALKING_WAKE;
	#else
	return FALSE;
	#endif
}

bool8 SpeciesHasPurifyingSalt(unusedArg u16 species)
{
	#if (defined SPECIES_NACLI && SPECIES_NACLSTACK && SPECIES_GARGANACL)
	return species == SPECIES_NACLI || species == SPECIES_NACLSTACK || species == SPECIES_GARGANACL;
	#else
	return FALSE;
	#endif
}

bool8 CheckStatusAny(u8 bank)
{
    return (gBattleMons[bank].status1 & STATUS1_ANY);
}

bool8 SpeciesHasRockyPayload(unusedArg u16 species)
{
	#ifdef SPECIES_BOMBIRDIER
	return species == SPECIES_BOMBIRDIER;
	#else
	return FALSE;
	#endif
}

bool8 SpeciesHasSeedSower(unusedArg u16 species)
{
	#ifdef SPECIES_ARBOLIVA
	return species == SPECIES_ARBOLIVA;
	#else
	return FALSE;
	#endif
}

bool8 SpeciesHasSharpness(unusedArg u16 species)
{
	#if (defined SPECIES_GALLADE && SPECIES_SAMUROTT_H && SPECIES_KLEAVOR && SPECIES_VELUZA)
	return species == SPECIES_GALLADE || species == SPECIES_SAMUROTT_H || species == SPECIES_KLEAVOR || species == SPECIES_VELUZA;
	#else
	return FALSE;
	#endif
}

bool8 SpeciesHasSupremeOverlord(unusedArg u16 species)
{
	#ifdef SPECIES_KINGAMBIT
	return species == SPECIES_KINGAMBIT;
	#else
	return FALSE;
	#endif
}

bool8 IsFaintedPokemonInParty(void)
{
    u8 i;
    struct Pokemon* party = gPlayerParty;
    u8 partyCount = gPlayerPartyCount;

    for (i = 0; i < partyCount; i++)
    {
        if (GetMonData(&party[i], MON_DATA_HP, NULL) == 0)
            return TRUE;
    }

    return FALSE;
}

bool8 SpeciesHasSuperSweetSyrup(unusedArg u16 species)
{
	#if (defined SPECIES_DIPPLIN && SPECIES_HYDRAPPLE)
	return species == SPECIES_DIPPLIN || species == SPECIES_HYDRAPPLE;
	#else
	return FALSE;
	#endif
}

bool8 SpeciesHasTeraShift(unusedArg u16 species)
{
	#if (defined SPECIES_TERAPAGOS && defined SPECIES_TERAPAGOS_TERASTAL)
	return species == SPECIES_TERAPAGOS || species == SPECIES_TERAPAGOS_TERASTAL;
	#else
	return FALSE;
	#endif
}

bool8 SpeciesHasTeraShell(unusedArg u16 species)
{
	#if (defined SPECIES_TERAPAGOS && defined SPECIES_TERAPAGOS_TERASTAL)
	return species == SPECIES_TERAPAGOS || species == SPECIES_TERAPAGOS_TERASTAL;
	#else
	return FALSE;
	#endif
}

bool8 SpeciesHasThermalExchange(unusedArg u16 species)
{
	#if (defined SPECIES_FRIGIBAX && SPECIES_ARCTIBAX && SPECIES_BAXCALIBUR)
	return species == SPECIES_FRIGIBAX || species == SPECIES_ARCTIBAX || species == SPECIES_BAXCALIBUR;
	#else
	return FALSE;
	#endif
}

bool8 SpeciesHasToxicChain(unusedArg u16 species)
{
	#if (defined SPECIES_OKIDOGI && SPECIES_FEZANDIPITI && SPECIES_MUNKIDORI)
	return species == SPECIES_OKIDOGI || species == SPECIES_FEZANDIPITI || species == SPECIES_MUNKIDORI;
	#else
	return FALSE;
	#endif
}

bool8 SpeciesHasPoisonPuppeteer(unusedArg u16 species)
{
	#ifdef SPECIES_PECHARUNT
	return species == SPECIES_PECHARUNT;
	#else
	return FALSE;
	#endif
}

bool8 SpeciesHasToxicDebris(unusedArg u16 species)
{
	#ifdef SPECIES_GLIMMORA
	return species == SPECIES_GLIMMORA;
	#else
	return FALSE;
	#endif
}

bool8 SpeciesHasWellBakedBody(unusedArg u16 species)
{
	#ifdef SPECIES_DACHSBUN
	return species == SPECIES_DACHSBUN;
	#else
	return FALSE;
	#endif
}

bool8 AngerShellStatsCheck(u8 bank)
{
    return (STAT_STAGE(bank, STAT_ATK) != STAT_STAGE_MAX
         || STAT_STAGE(bank, STAT_SPATK) != STAT_STAGE_MAX
         || STAT_STAGE(bank, STAT_SPEED) != STAT_STAGE_MAX
         || STAT_STAGE(bank, STAT_DEF) > STAT_STAGE_MIN
         || STAT_STAGE(bank, STAT_SPDEF) > STAT_STAGE_MIN);
}

bool8 SpeciesHasWindPower(unusedArg u16 species)
{
	#if (defined SPECIES_WATTREL && SPECIES_KILOWATTREL)
	return species == SPECIES_WATTREL || species == SPECIES_KILOWATTREL;
	#else
	return FALSE;
	#endif
}

bool8 SpeciesHasWindRider(unusedArg u16 species)
{
	#if (defined SPECIES_BRAMBLIN && SPECIES_BRAMBLEGHAST && SPECIES_SHIFTRY)
	return species == SPECIES_BRAMBLIN || species == SPECIES_BRAMBLEGHAST || species == SPECIES_SHIFTRY;
	#else
	return FALSE;
	#endif
}

bool8 SpeciesHasZerotoHero(unusedArg u16 species) //Custom Unbound Ability
{
	#if (defined SPECIES_PALAFIN && defined SPECIES_PALAFIN_HERO)
	return species == SPECIES_PALAFIN || species == SPECIES_PALAFIN_HERO;
	#else
	return FALSE;
	#endif
}
