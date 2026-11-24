package main

// tsk-go fork (fork fix 7, CLAUDE.md "Fork fixes"): the tests of way.go's clearlyNearestWay and state.go's
// holdStoppedRoad, kept out of upstream's road_ambiguity_test.go (they use its synthetic ways).

import (
	"math"
	"testing"
	"time"

	"pfeifer.dev/mapd/cereal"
	"pfeifer.dev/mapd/cereal/custom"
	"pfeifer.dev/mapd/maps"
	m "pfeifer.dev/mapd/math"
	ms "pfeifer.dev/mapd/settings"
)

// tsk-go fork (Nov 2026): a boulevard's main road and its service roads share the 2x envelope; with a fix good enough
// to tell them apart the nearest road is matched, and roads too close for the fix stay ambiguous.
func TestPackedClearlyNearestRoadWithPreciseFix(t *testing.T) {
	width := ms.Settings.DefaultLaneWidth
	ms.Settings.DefaultLaneWidth = 3.7 // the bundled default; the envelope depends on it
	defer func() { ms.Settings.DefaultLaneWidth = width }()
	main := syntheticWay{1, 11.2, 35.1, -97.9, 35.2, -97.9, false, 2}
	service := syntheticWay{2, 11.2, 35.1, -97.89975, 35.2, -97.89975, false, 2} // ~23 m east, inside the 2x envelope
	close := syntheticWay{3, 13.4, 35.1, -97.8999, 35.2, -97.8999, false, 2}     // ~9 m east
	for _, tc := range []struct {
		name  string
		ways  []syntheticWay
		acc   float32
		match bool
	}{
		{"rtk, service road 23 m away", []syntheticWay{main, service}, 0.2, true},
		{"5 m fix, service road 23 m away", []syntheticWay{main, service}, 5, true},
		{"rtk, road 9 m away", []syntheticWay{main, close}, 0.2, true},
		{"5 m fix, road 9 m away", []syntheticWay{main, close}, 5, false},
		{"no accuracy", []syntheticWay{main, close}, 0, false},
	} {
		t.Run(tc.name, func(t *testing.T) {
			s := State{}
			s.Init()
			s.bootNow = func() uint64 { return 10_100_000_000 }
			tile := packedRoadTile(t, tc.ways)
			sample := ambiguitySample(t, 10_000_000_000, true)
			sample.Location.SetHorizontalAccuracy(tc.acc)
			if n := len(plausibleLoadedWays(&tile, sample.Location)); n != 2 {
				t.Fatalf("both roads must be candidates, got %d", n)
			}
			s.ProcessGps(sample, true, func(m.Position) (maps.Offline, error) { return tile, nil }, time.Unix(0, 0))
			event, out := decodedOutput(t, &s)
			if tc.match && (!event.Valid() || out.WayId() != 1 || out.SpeedLimit() != 11.2) {
				t.Fatalf("nearest road not matched: status=%v way=%d", out.RoadStatus(), out.WayId())
			}
			if !tc.match && (event.Valid() || out.RoadStatus() != custom.MapdOut_SampleStatus_unknown) {
				t.Fatalf("close roads resolved: status=%v way=%d", out.RoadStatus(), out.WayId())
			}
		})
	}
}

// tsk-go fork (Nov 2026): the RTK phone handoff has no heading while stopped; standing still on the matched road keeps
// it, moving off it or a CAN fix without heading does not.
func TestPhoneStoppedKeepsMatchedRoad(t *testing.T) {
	road := syntheticWay{1, 11.2, 35.1, -97.9, 35.2, -97.9, false, 2}
	tile := packedRoadTile(t, []syntheticWay{road})
	loader := func(m.Position) (maps.Offline, error) { return tile, nil }
	fix := uint64(10_000_000_000)
	s := State{}
	s.Init()
	s.bootNow = func() uint64 { return fix + 100_000_000 }
	sample := syntheticSample(t, cereal.GpsSourcePhone, fix, 1, true, true)
	sample.Location.SetHorizontalAccuracy(0.2)
	sample.Location.SetBearingAccuracyDeg(2)
	sample.Location.SetSpeed(5)
	sample.Location.SetSpeedAccuracy(0.3)
	s.ProcessGps(sample, true, loader, time.Unix(0, 0))
	if _, out := decodedOutput(t, &s); out.RoadStatus() != custom.MapdOut_SampleStatus_matchedLimit {
		t.Fatalf("moving phone fix not matched: %v", out.RoadStatus())
	}
	stopped := syntheticSample(t, cereal.GpsSourcePhone, fix+200_000_000, 1, false, true)
	stopped.Location.SetHorizontalAccuracy(0.2)
	stopped.Location.SetBearingAccuracyDeg(float32(math.NaN()))
	stopped.Location.SetSpeed(0.1)
	stopped.Location.SetSpeedAccuracy(0.3)
	s.bootNow = func() uint64 { return fix + 300_000_000 }
	s.ProcessGps(stopped, true, loader, time.Unix(0, 0))
	if ev, out := decodedOutput(t, &s); !ev.Valid() || out.RoadStatus() != custom.MapdOut_SampleStatus_matchedLimit || out.SpeedLimit() != 11.2 {
		t.Fatalf("stopped on the road lost it: %v", out.RoadStatus())
	}
	creeping := syntheticSample(t, cereal.GpsSourcePhone, fix+400_000_000, 1, false, true)
	creeping.Location.SetHorizontalAccuracy(0.2)
	creeping.Location.SetBearingAccuracyDeg(float32(math.NaN()))
	creeping.Location.SetSpeed(3)
	creeping.Location.SetSpeedAccuracy(0.3)
	s.bootNow = func() uint64 { return fix + 500_000_000 }
	s.ProcessGps(creeping, true, loader, time.Unix(0, 0))
	if _, out := decodedOutput(t, &s); out.RoadStatus() != custom.MapdOut_SampleStatus_noMatch {
		t.Fatalf("moving without heading kept the road: %v", out.RoadStatus())
	}
}
