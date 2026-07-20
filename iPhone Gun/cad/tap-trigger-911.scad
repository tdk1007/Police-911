// ============================================================
// TAP-TRIGGER 911 — iPhone 17 Pro light-gun grip
// Phone sits landscape, on edge, screen facing RIGHT.
// Index finger rests on the shelf under the screen and curls
// up/inward to tap-fire — same motion as pulling a trigger.
//
// Print: lying on its flat LEFT side. Supports needed only
// under the two thin cradle lips.
// Left-handed? Wrap everything in mirror([1,0,0]).
// ============================================================
$fn = 64;

/* ---------------- tune here ---------------- */
phone_l   = 150;    // iPhone 17 Pro length
phone_h   = 72;     // width (= height when landscape)
phone_t   = 8.75;   // thickness — set ~10.8-11.5 if a slim case stays on
clr_t     = 0.5;    // depth clearance behind phone
lip_gap   = 0.4;    // air gap between glass and lips
lip_over  = 2.3;    // how far lips overlap the glass edge (top/bottom only)
lip_t     = 2.2;    // lip wall thickness
headroom  = 3.2;    // lift room in top channel for insert/remove
rib_h     = 0.5;    // crush ribs on back wall (anti-rattle)
rake      = 16;     // grip rake angle, degrees
show_phone = true;  // ghost phone in preview (never exported)

/* ---------------- layout (derived) ---------------- */
screen_x = 8;                        // X of the glass plane
flat_x   = -16.5;                    // flat left face = print bed
floor_z  = -26.4;                    // cavity floor (phone bottom edge)
rear_y   = 18;                       // phone rear end
cav_back = screen_x - phone_t - clr_t;
ceil_z   = floor_z + phone_h + headroom;
seat_top = floor_z + phone_h;
lip_in   = screen_x + lip_gap;
lip_out  = lip_in + lip_t;
top_z    = ceil_z + 4;               // spine top
bot_z    = floor_z - 5.6;            // spine bottom
rail_y1  = 112;                      // rails end here; camera end hangs free
slab_w   = cav_back - flat_x;
tr       = tan(rake);

/* ================= grip ================= */
// cross-section: flat left face (bed side), rounded right side
module sec2d(cy, d, w) {
    rr = 10;
    offset(r = 2) hull() {
        translate([flat_x + w - rr, cy - (d/2 - rr)]) circle(rr - 2);
        translate([flat_x + w - rr, cy + (d/2 - rr)]) circle(rr - 2);
        translate([flat_x + 2, cy - d/2 + 2]) square([2, d - 4]);
    }
}
module gslice(zz, d, w) {
    translate([0, 0, zz]) linear_extrude(0.2) sec2d(-32 + tr*zz, d, w);
}
module grip() {
    hull() { gslice(0, 48, 29);     gslice(-3, 52, 33);  }
    hull() { gslice(-3, 52, 33);    gslice(-30, 53, 34); }
    hull() { gslice(-30, 53, 34);   gslice(-60, 55, 35); }   // palm swell
    hull() { gslice(-60, 55, 35);   gslice(-95, 53, 33); }
    hull() { gslice(-95, 53, 33);   gslice(-104.8, 50, 31); }
    // beavertail — nestles the web of the hand
    hull() {
        translate([flat_x, -62, -2.5]) cube([26, 8, 2.5]);
        translate([flat_x, -68, -6])   cube([20, 6, 2]);
    }
}

/* ================= frame ================= */
module frame() {
    // spine slab behind the phone
    translate([flat_x, 14, bot_z])
        cube([slab_w, rail_y1 - 14, top_z - bot_z]);
    // bridge: grip top -> spine
    translate([flat_x, -12, -14]) cube([slab_w, 28, 14]);
    // guard blade: grip front -> spine bottom (stiffener; middle finger
    // rides under it like a trigger guard, index finger passes right of it)
    translate([flat_x, 0, 0]) rotate([90, 0, 90]) linear_extrude(18.5)
        polygon([[-18,-24], [-17,-46], [24,-44], [31,-34], [31,-24]]);
}

/* ================= cradle ================= */
module cradle() {
    // bottom rail + lip
    translate([cav_back, rear_y, bot_z])
        cube([lip_out - cav_back, rail_y1 - rear_y, floor_z - bot_z]);
    translate([lip_in, rear_y, floor_z])
        cube([lip_t, rail_y1 - rear_y, lip_over]);
    // top rail + lip
    translate([cav_back, rear_y, ceil_z])
        cube([lip_out - cav_back, rail_y1 - rear_y, top_z - ceil_z]);
    translate([lip_in, rear_y, seat_top - lip_over])
        cube([lip_t, rail_y1 - rear_y, ceil_z - (seat_top - lip_over)]);
    // rear end stop (stops short of the screen plane — finger clearance)
    translate([cav_back, 14, bot_z]) cube([4 - cav_back, 4, top_z - bot_z]);
    // crush ribs — snug the phone against the lips
    for (yy = [28, 58, 88])
        translate([cav_back - 0.1, yy, -20]) cube([rib_h + 0.1, 3, 60]);
    // trigger-finger shelf: rest here, curl up to tap
    hull() {
        translate([11.3, 26, -31]) sphere(3);
        translate([11.3, 64, -31]) sphere(3);
    }
}

/* ================= cuts ================= */
module cuts() {
    // USB-C pass-through in the end stop
    translate([cav_back - 1, 11, floor_z + phone_h/2 - 8]) cube([7, 8, 16]);
    // lanyard hole in the butt
    translate([-25, -58, -94]) rotate([0, 90, 0]) cylinder(h = 50, r = 3.5);
    // lip lead-in chamfers (insert/remove)
    translate([0, rail_y1 + 0.5, 0]) rotate([90, 0, 0])
        linear_extrude(rail_y1 - rear_y + 1) polygon([
            [lip_in - 0.01, seat_top - lip_over - 0.01],
            [lip_in + 1.6,  seat_top - lip_over - 0.01],
            [lip_in - 0.01, seat_top - lip_over + 1.6]]);
    translate([0, rail_y1 + 0.5, 0]) rotate([90, 0, 0])
        linear_extrude(rail_y1 - rear_y + 1) polygon([
            [lip_in - 0.01, floor_z + lip_over + 0.01],
            [lip_in + 1.6,  floor_z + lip_over + 0.01],
            [lip_in - 0.01, floor_z + lip_over - 1.6]]);
    // front facets on the spine (style + fewer sharp corners)
    translate([flat_x - 1, 0, 0]) rotate([90, 0, 90]) linear_extrude(slab_w + 32)
        polygon([[94, top_z + 0.1], [rail_y1 + 1, top_z + 0.1], [rail_y1 + 1, top_z - 19]]);
    translate([flat_x - 1, 0, 0]) rotate([90, 0, 90]) linear_extrude(slab_w + 32)
        polygon([[rail_y1 + 1, bot_z - 0.1], [rail_y1 + 1, bot_z + 17], [95, bot_z - 0.1]]);
    // rubber-band groove ring (optional retention strap near muzzle end)
    translate([flat_x - 1, 88, top_z - 1.2])  cube([lip_out - flat_x + 2, 3, 5]);
    translate([flat_x - 1, 88, bot_z - 3.8])  cube([lip_out - flat_x + 2, 3, 5]);
    translate([lip_out - 1.2, 88, bot_z - 1]) cube([6, 3, top_z - bot_z + 2]);
}

/* ================= build ================= */
difference() {
    union() { grip(); frame(); cradle(); }
    cuts();
}

// ghost phone — camera end forward, USB-C at the end stop
if (show_phone)
    %translate([screen_x - phone_t, rear_y, floor_z])
        cube([phone_t, phone_l, phone_h]);
