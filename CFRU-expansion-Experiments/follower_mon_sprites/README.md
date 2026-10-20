# Follower-mon overworld sprites

The indexed PNG files in this directory replace the old `followermon_Sprites`
entry from `free_bytereplacements`.

- Keep every image in indexed (`P`) mode with palette indexes from 0 to 15.
- Keep each image's current dimensions. Regular sheets are 32x192 and compile
  to `0xC00` bytes; 64x64 sheets are 64x384 and compile to `0x3000` bytes.
- A few regular sheets have an additional `.padding.bin` file to preserve gaps
  present in the original fixed-address layout. Do not edit those files.
- Do not reorder or manually change offsets in `manifest.txt` unless the
  corresponding symbols and binary layout are intentionally being changed.
- Set `MON_OW_OFFSET` to the same ROM file offset in `scripts/build.py` and
  `scripts/insert.py` before building and inserting.

`scripts/build.py` creates `build/follower_mon_sprites.bin` and absolute linker
symbols for every `gFollowingMonPic_*Tiles` declaration. `scripts/insert.py`
inserts that binary at `MON_OW_OFFSET` and checks that it does not overlap the
main code insertion.
