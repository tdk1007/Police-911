// Earpiece F-009: tests for the fork's live VR knobs (pcsx2/GS/VR/VRKnobs.h, from
// vr/pcsx2-knobs.patch) without building PCSX2. Run: py vr/vr_knobs_selftest.py
//
// The byte vectors are the same ones Earpiece's FakePine is tested against
// (earpiece-proto/tests/test_game_contract.py::test_fake_pine_vr_knob_opcodes_match_the_fork),
// so the fork and the fake the adapter is tested on answer alike.

#include "GS/VR/VRKnobs.h"

#include <cmath>
#include <cstdio>
#include <cstring>
#include <limits>
#include <thread>
#include <vector>

namespace
{
	int failures = 0;

	void Check(bool ok, const char* what)
	{
		std::printf("%s  %s\n", ok ? "PASS" : "FAIL", what);
		if (!ok)
			failures++;
	}

	std::vector<std::uint8_t> Hex(const char* s)
	{
		std::vector<std::uint8_t> out;
		const auto nibble = [](char c) { return c <= '9' ? c - '0' : (c | 0x20) - 'a' + 10; };
		for (; s[0] && s[1]; s += 2)
			out.push_back(static_cast<std::uint8_t>(nibble(s[0]) * 16 + nibble(s[1])));
		return out;
	}

	// One command as PINE.cpp runs it: the reply payload, or false for IPC_FAIL.
	bool Ask(VRKnobs::Table& t, const std::vector<std::uint8_t>& cmd, std::vector<std::uint8_t>* reply)
	{
		const std::uint8_t op = cmd[0];
		if (op != VRKnobs::OpSet && op != VRKnobs::OpGet && op != VRKnobs::OpList)
			return false;
		if (cmd.size() != 1 + VRKnobs::ArgBytes(op))
			return false; // PINE.cpp's SafetyChecks: a short command never reaches Run
		reply->assign(VRKnobs::ReplyBytes(op), 0xCD);
		return VRKnobs::Run(t, op, cmd.data() + 1, reply->data());
	}

	std::vector<std::uint8_t> SetCmd(std::uint8_t id, float v)
	{
		std::vector<std::uint8_t> c = {VRKnobs::OpSet, id, 0, 0, 0, 0};
		std::memcpy(&c[2], &v, 4);
		return c;
	}

	float GetValue(VRKnobs::Table& t, std::uint8_t id)
	{
		std::vector<std::uint8_t> r;
		if (!Ask(t, {VRKnobs::OpGet, id}, &r))
			return std::numeric_limits<float>::quiet_NaN();
		float v;
		std::memcpy(&v, r.data(), 4);
		return v;
	}
} // namespace

int main()
{
	VRKnobs::Table t;
	t.Seed(VRKnobs::UnitsPerMetre, 100.0f);
	t.Seed(VRKnobs::FlatWidth, 3.0f);
	std::vector<std::uint8_t> r;

	Check(Ask(t, {VRKnobs::OpList}, &r) &&
			  r == Hex("02000000"
					   "02" "00002041" "00007a44" "0000c842"
					   "05" "0000003f" "00002041" "00004040"),
		"List: count, then id, lo, hi, value for world scale and overlay width");

	Check(Ask(t, Hex("300500005040"), &r) && r.empty(), "Set flat width 3.25 answers OK, no payload");
	Check(Ask(t, {VRKnobs::OpGet, 5}, &r) && r == Hex("00005040"), "Get flat width reads 3.25 back");

	Check(Ask(t, SetCmd(2, 5000.0f), &r) && GetValue(t, 2) == 1000.0f, "an out-of-range Set is clamped to hi");
	Check(Ask(t, SetCmd(5, -1.0f), &r) && GetValue(t, 5) == 0.5f, "a negative Set is clamped to lo");
	Check(Ask(t, SetCmd(5, 1e30f), &r) && GetValue(t, 5) == 10.0f, "a huge Set is clamped to hi");

	const float before = GetValue(t, 5);
	const float bad[] = {std::numeric_limits<float>::quiet_NaN(), std::numeric_limits<float>::infinity(),
		-std::numeric_limits<float>::infinity()};
	bool refused = true;
	for (float v : bad)
		refused = refused && !Ask(t, SetCmd(5, v), &r);
	Check(refused && GetValue(t, 5) == before, "NaN and infinities FAIL and change nothing");

	Check(!Ask(t, SetCmd(9, 1.0f), &r), "Set of an unknown knob id FAILs");
	Check(!Ask(t, {VRKnobs::OpGet, 1}, &r), "Get of a knob this build doesn't serve (ipd_scale) FAILs");
	Check(!Ask(t, {VRKnobs::OpSet, 5, 0}, &r), "a truncated Set FAILs");

	VRKnobs::Table seeded;
	seeded.Seed(VRKnobs::FlatWidth, std::numeric_limits<float>::quiet_NaN());
	seeded.Seed(VRKnobs::UnitsPerMetre, 1e9f);
	Check(seeded.Value(VRKnobs::FlatWidth) == 2.4f && seeded.Value(VRKnobs::UnitsPerMetre) == 1000.0f,
		"a bad ini value keeps the default (NaN) or is clamped (too big)");

	// Set from the PINE thread while the EE and GS threads read every vsync: every read is a
	// value that was set, never a torn one.
	VRKnobs::Table shared;
	std::atomic<bool> stop{false};
	bool torn = false;
	std::thread reader([&] {
		while (!stop.load())
		{
			const float v = shared.Value(VRKnobs::FlatWidth);
			torn = torn || !(v == 2.4f || v == 0.5f || v == 10.0f);
		}
	});
	for (int i = 0; i < 200000; i++)
		shared.Set(VRKnobs::FlatWidth, i % 2 ? 0.5f : 10.0f);
	stop.store(true);
	reader.join();
	Check(!torn, "concurrent Set and read never see a torn value");

	std::printf("%s (%d failed)\n", failures ? "FAIL" : "PASS", failures);
	return failures ? 1 : 0;
}
