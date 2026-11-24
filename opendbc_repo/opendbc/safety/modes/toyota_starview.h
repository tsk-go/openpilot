#pragma once

// StarView (fork patches 46-49, 53; CLAUDE.md "Fork history" 29 and 33), kept out of toyota.h so a sync meets only
// the few lines in toyota_tx_hook that use these. The 4th-gen Sienna's Main Body module refuses the KWP door command
// (7F 30 11) and takes the UDS active test instead - extended session, 2F 2810 (lock) / 2F 2811 (unlock) on, then back
// to the module; the answer-back is the module's own wireless buzzer (2F 284A) or the horn (2F 2802). Exact frames
// only, sub-address 0x40 (Main Body), on 0x750 bus 0.
// Macros, not functions: toyota_tx_hook then compiles to exactly the code it did when these lists were written in it,
// so the panda image built from this source equals the one driven on the car (CLAUDE.md "Panda firmware").

// The frames that start something: allowed behind upstream's stationary gate, like its own body commands.
#define TOYOTA_STARVIEW_DOOR_START(payload) \
  (((payload) == 0x0000000003100240ULL) ||   /* 40 02 10 03: extended session */ \
   ((payload) == 0x80010310282F0640ULL) ||   /* 40 06 2F 28 10 03 01 80: lock on */ \
   ((payload) == 0x80010311282F0640ULL) ||   /* 40 06 2F 28 11 03 01 80: unlock on */ \
   ((payload) == 0x8001034A282F0640ULL) ||   /* 40 06 2F 28 4A 03 01 80: wireless buzzer on */ \
   ((payload) == 0x80010302282F0640ULL))     /* 40 06 2F 28 02 03 01 80: horn on */

// Handing control back (or reading a lock state) can only make things safer: allowed whenever the relay is fine,
// moving or not.
#define TOYOTA_STARVIEW_DOOR_RETURN(payload) \
  (((payload) == 0x00800010282F0540ULL) ||  /* 40 05 2F 28 10 00 80: lock back to the module */ \
   ((payload) == 0x00800011282F0540ULL) ||  /* 40 05 2F 28 11 00 80: unlock back to the module */ \
   ((payload) == 0x0080004A282F0540ULL) ||  /* 40 05 2F 28 4A 00 80: buzzer back to the module */ \
   ((payload) == 0x00800002282F0540ULL) ||  /* 40 05 2F 28 02 00 80: horn back to the module */ \
   ((payload) == 0x0000000001100240ULL) ||  /* 40 02 10 01: default session */ \
   ((payload) == 0x00000000003E0240ULL) ||  /* 40 02 3E 00: tester present */ \
   /* StarLock's real lock state - read only (40 03 22 10 xx): driver, passenger, sliding doors, back door */ \
   ((payload) == 0x0000001A10220340ULL) || ((payload) == 0x0000001910220340ULL) || \
   ((payload) == 0x0000001B10220340ULL) || ((payload) == 0x0000001C10220340ULL) || \
   ((payload) == 0x0000001E10220340ULL))
