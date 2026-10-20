.text
.thumb
.align 2

.include "../asm_defines.s"
.include "../battle_script_macros.s"

.global BattleScript_Terastallize

BattleScript_Terastallize:
	setword BATTLE_STRING_LOADER gText_TeraReactingString
	printstring 0x184
	waitmessage DELAY_HALFSECOND

TeraAnimBS:
	playanimation BANK_SCRIPTING ANIM_TERASTAL 0x0
	callasm BackupScriptingBankMoveSelectionCursor
	waitstateatk
	reloadhealthbar BANK_SCRIPTING
	callasm RefreshFormChangeHealthbox
	setword BATTLE_STRING_LOADER gText_TeraCompletedString
	printstring 0x184
	waitmessage DELAY_1SECOND
	callasm TryActivateTeraFormAbility
	end3
