-- Police 911 (p911ud) body-sensor emulation for MAME 0.289.
--
-- The cabinet's overhead sensor unit talks to the game over PC16552 DUART
-- channel B. The game's channel-B interrupt handler fills a 1 KB receive ring;
-- this script writes sensor packets straight into that ring, so the game sees
-- a working sensor without any MAME source changes. Protocol and addresses:
-- see ../ARCADE_FINDINGS.md.
--
-- Packet (4 bytes): b0, b1 = 6-bit sensor-bar bitmaps (top two bits clear);
--                   b2, b3 = left/right range readings (>= 0x20; 0x20 = no echo).
-- The game derives head X from (b2 - b3) and height from (b2 + b3).

local sp = manager.machine.devices[':maincpu'].spaces['program']

local RING    = 0x33EBE8  -- *(r2+0x5C) + 0x400, r2 = 0x000DCDF4 in the game module
local RING_RD = 0x868     -- u16 read index (game advances it)
local RING_WR = 0x86A     -- u16 write index (we advance it)
local SENSOR  = 0x33EFE8  -- *(r2+0x60): sensor driver struct

-- Current body pose fed to the game. Other scripts/bridges can change these
-- through the globals below (e.g. from a webcam tracker).
p911 = p911 or {}
p911.left  = 0x60   -- b2: left rangefinder
p911.right = 0x60   -- b3: right rangefinder
p911.barsA = 0x0C   -- b0
p911.barsB = 0x0C   -- b1

local function push(b)
  local wr = sp:read_u16(RING_WR)
  sp:write_u8(RING + wr, b)
  sp:write_u16(RING_WR, (wr + 1) & 0x3FF)
end

local function clamp_range(v)
  v = math.floor(v + 0.5)
  if v < 0x21 then v = 0x21 end   -- 0x20 means "no echo"
  if v > 0xFC then v = 0xFC end   -- parser rejects >= 0xFD
  return v
end

local armed, last_frame = false, -1
emu.register_periodic(function()
  local fn = manager.machine.screens:at(1):frame_number()
  if fn == last_frame then return end
  last_frame = fn
  -- Wait until the game has loaded and its sensor driver struct exists;
  -- writing into this RAM earlier corrupts the boot.
  if not armed then
    if fn > 300 and sp:read_u32(SENSOR) ~= 0
       and sp:read_u16(RING_WR) < 0x400 and sp:read_u16(RING_RD) < 0x400 then
      armed = true
      emu.print_info('p911_sensor: armed at frame ' .. fn)
    else
      return
    end
  end
  local used = (sp:read_u16(RING_WR) - sp:read_u16(RING_RD)) & 0x3FF
  if used < 0x100 then
    push(p911.barsA & 0x3F)
    push(p911.barsB & 0x3F)
    push(clamp_range(p911.left))
    push(clamp_range(p911.right))
  end
end)
