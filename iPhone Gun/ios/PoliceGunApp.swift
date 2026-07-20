//  PoliceGunApp.swift
//  PoliceGun v1.0 — iPhone gyro light gun (Spike 1)
//
//  Reads the gyro, converts angular velocity into relative mouse deltas, and
//  streams them over UDP (~100 Hz) to gun_helper.py on the Windows PC. A plain
//  relative mouse is exactly what Police 911 (PS2/PCSX2) consumes to move the
//  crosshair and fire, so this app is just "a mouse you point at the TV."
//
//  ZERO-COST TRIGGERS (no hardware needed to validate the spike):
//    • Tap    — tap the phone body; an accelerometer spike fires. Best rapid fire.
//    • Volume — press a volume button; caught via AVAudioSession KVO (sideload-only).
//    • Screen — the on-screen FIRE pad; also supports hold-to-autofire.
//  Turn on whichever you like in the Trigger section; they stack.
//
//  SETUP (Xcode):
//   1. New Project → iOS → App → name "PoliceGun", interface SwiftUI, Swift.
//   2. Replace the generated App file's contents with this file.
//   3. Signing: pick your personal team. Deploy target iOS 16+.
//   4. Run on the physical iPhone (gyro/accelerometer aren't in the simulator).

import SwiftUI
import CoreMotion
import Network
import AVFoundation
import MediaPlayer
import UIKit
import QuartzCore

// MARK: - Networking

final class UDPGunClient {
    private var connection: NWConnection?

    func connect(host: String, port: UInt16) {
        connection?.cancel()
        guard let nwPort = NWEndpoint.Port(rawValue: port) else { return }
        let conn = NWConnection(host: NWEndpoint.Host(host), port: nwPort, using: .udp)
        conn.start(queue: .global(qos: .userInteractive))
        connection = conn
    }

    func send(dx: Double, dy: Double, fire: Bool) {
        guard let connection else { return }
        let json = "{\"dx\":\(String(format: "%.3f", dx)),\"dy\":\(String(format: "%.3f", dy)),\"fire\":\(fire ? 1 : 0)}"
        connection.send(content: json.data(using: .utf8), completion: .idempotent)
    }
}

// MARK: - System volume plumbing (for the volume-button trigger)

/// Holds a reference to the hidden MPVolumeView's slider so we can reset the
/// system volume to mid-scale after each press (keeps headroom for the next one).
final class SystemVolume {
    static let shared = SystemVolume()
    weak var slider: UISlider?
    func set(_ v: Float) {
        DispatchQueue.main.async {
            self.slider?.value = v
            self.slider?.sendActions(for: .valueChanged)
        }
    }
}

/// Off-screen MPVolumeView. Its presence also suppresses the system volume HUD.
struct HiddenVolumeView: UIViewRepresentable {
    func makeUIView(context: Context) -> MPVolumeView {
        let v = MPVolumeView(frame: CGRect(x: -3000, y: -3000, width: 1, height: 1))
        v.alpha = 0.0001
        DispatchQueue.main.async {
            SystemVolume.shared.slider = v.subviews.compactMap { $0 as? UISlider }.first
        }
        return v
    }
    func updateUIView(_ uiView: MPVolumeView, context: Context) {}
}

// MARK: - Motion → deltas + triggers

final class GunController: ObservableObject {
    private let motion = CMMotionManager()
    private let client = UDPGunClient()

    // Connection
    @AppStorage("host") var host: String = "192.168.0.50"
    @AppStorage("port") var port: Int = 52777

    // Feel
    @AppStorage("sensitivity") var sensitivity: Double = 900   // counts per rad
    @AppStorage("invertX") var invertX: Bool = false
    @AppStorage("invertY") var invertY: Bool = true
    @AppStorage("swapAxes") var swapAxes: Bool = false
    @AppStorage("deadzone") var deadzone: Double = 0.01        // rad/s

    // Triggers
    @AppStorage("triggerTap") var triggerTap: Bool = true
    @AppStorage("triggerVolume") var triggerVolume: Bool = false
    @AppStorage("tapThreshold") var tapThreshold: Double = 1.2 // g of userAcceleration

    @Published var running = false
    @Published var fire = false
    @Published var lastDX: Double = 0
    @Published var lastDY: Double = 0
    @Published var tapFlash = false

    // Smoothing / gating state
    private var smoothX = 0.0
    private var smoothY = 0.0
    private let smoothing = 0.35
    private var lastTapTime: CFTimeInterval = 0
    private var motionMuteUntil: CFTimeInterval = 0
    private var pulseToken = 0

    // Volume trigger state
    private let audioSession = AVAudioSession.sharedInstance()
    private var volumeObserver: NSKeyValueObservation?
    private var ignoreVolumeUntil: CFTimeInterval = 0

    func start() {
        client.connect(host: host, port: UInt16(port))
        startVolumeTrigger()
        guard motion.isDeviceMotionAvailable else { return }
        motion.deviceMotionUpdateInterval = 1.0 / 100.0
        motion.startDeviceMotionUpdates(using: .xArbitraryZVertical,
                                        to: .main) { [weak self] dm, _ in
            guard let self, let dm else { return }
            self.tick(dm)
        }
        running = true
    }

    func stop() {
        motion.stopDeviceMotionUpdates()
        stopVolumeTrigger()
        running = false
        client.send(dx: 0, dy: 0, fire: false)
    }

    // MARK: Fire

    /// Momentary fire: mouse down now, up shortly after. Repeated pulses just
    /// re-arm the timer, so rapid taps produce rapid distinct clicks.
    private func firePulse() {
        fire = true
        pulseToken += 1
        let token = pulseToken
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.045) {
            if token == self.pulseToken { self.fire = false }
        }
    }

    /// Held fire (the on-screen pad): mouse stays down while held.
    func setHeldFire(_ down: Bool) { fire = down }

    // MARK: Volume-button trigger

    private func startVolumeTrigger() {
        try? audioSession.setCategory(.playback, options: [.mixWithOthers])
        try? audioSession.setActive(true)
        volumeObserver = audioSession.observe(\.outputVolume, options: [.new]) {
            [weak self] _, _ in
            guard let self, self.triggerVolume else { return }
            let now = CACurrentMediaTime()
            if now < self.ignoreVolumeUntil { return }   // ignore our own reset
            self.firePulse()
            self.ignoreVolumeUntil = now + 0.20
            SystemVolume.shared.set(0.5)                 // re-center for next press
        }
    }

    private func stopVolumeTrigger() {
        volumeObserver = nil
        try? audioSession.setActive(false)
    }

    // MARK: Per-frame

    private func tick(_ dm: CMDeviceMotion) {
        let now = CACurrentMediaTime()

        // --- tap-to-fire: sharp linear-acceleration spike ---
        if triggerTap {
            let a = dm.userAcceleration
            let mag = (a.x * a.x + a.y * a.y + a.z * a.z).squareRoot()
            if mag > tapThreshold && now - lastTapTime > 0.12 {
                lastTapTime = now
                motionMuteUntil = now + 0.06   // don't let the tap jerk the aim
                firePulse()
                flashTap()
            }
        }

        // --- aim: angular velocity → relative deltas ---
        var yaw = dm.rotationRate.y
        var pitch = dm.rotationRate.x
        if swapAxes { swap(&yaw, &pitch) }
        yaw = abs(yaw) < deadzone ? 0 : yaw
        pitch = abs(pitch) < deadzone ? 0 : pitch
        smoothX = smoothX * smoothing + yaw * (1 - smoothing)
        smoothY = smoothY * smoothing + pitch * (1 - smoothing)

        let dt = motion.deviceMotionUpdateInterval
        var dx = smoothX * sensitivity * dt
        var dy = smoothY * sensitivity * dt
        if invertX { dx = -dx }
        if invertY { dy = -dy }
        if now < motionMuteUntil { dx = 0; dy = 0 }   // mute aim during a tap

        lastDX = dx
        lastDY = dy
        client.send(dx: dx, dy: dy, fire: fire)
    }

    private func flashTap() {
        tapFlash = true
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.08) { self.tapFlash = false }
    }
}

// MARK: - UI

struct ContentView: View {
    @StateObject private var gun = GunController()

    var body: some View {
        NavigationStack {
            Form {
                Section("Connection") {
                    HStack {
                        Text("PC IP")
                        TextField("192.168.0.50", text: $gun.host)
                            .keyboardType(.numbersAndPunctuation)
                            .autocorrectionDisabled()
                            .textInputAutocapitalization(.never)
                            .multilineTextAlignment(.trailing)
                    }
                    HStack {
                        Text("Port")
                        TextField("52777", value: $gun.port, format: .number)
                            .keyboardType(.numberPad)
                            .multilineTextAlignment(.trailing)
                    }
                }

                Section("Feel") {
                    VStack(alignment: .leading) {
                        Text("Sensitivity \(Int(gun.sensitivity))")
                        Slider(value: $gun.sensitivity, in: 200...2500)
                    }
                    Toggle("Invert X", isOn: $gun.invertX)
                    Toggle("Invert Y", isOn: $gun.invertY)
                    Toggle("Swap axes", isOn: $gun.swapAxes)
                }

                Section("Trigger (pick any — all free)") {
                    Toggle("Tap to fire", isOn: $gun.triggerTap)
                    if gun.triggerTap {
                        VStack(alignment: .leading) {
                            Text(String(format: "Tap sensitivity  (%.1f g)", gun.tapThreshold))
                            // Lower threshold = easier taps. Invert slider for intuition.
                            Slider(value: $gun.tapThreshold, in: 0.5...3.0)
                        }
                    }
                    Toggle("Volume button to fire", isOn: $gun.triggerVolume)
                }

                Section("Live") {
                    HStack {
                        Text(String(format: "dx %+.2f   dy %+.2f", gun.lastDX, gun.lastDY))
                            .font(.system(.body, design: .monospaced))
                        Spacer()
                        Circle()
                            .fill(gun.fire || gun.tapFlash ? Color.red : Color.gray.opacity(0.3))
                            .frame(width: 18, height: 18)
                    }
                    Text(gun.running ? "STREAMING" : "stopped")
                        .foregroundStyle(gun.running ? .green : .secondary)
                }

                Section {
                    Button(gun.running ? "Stop" : "Start") {
                        gun.running ? gun.stop() : gun.start()
                    }
                    .frame(maxWidth: .infinity)
                    .tint(gun.running ? .red : .green)
                }

                Section("On-screen FIRE (hold = autofire)") {
                    Text("FIRE")
                        .font(.largeTitle.bold())
                        .frame(maxWidth: .infinity, minHeight: 110)
                        .background(gun.fire ? Color.red : Color.gray.opacity(0.3))
                        .foregroundStyle(.white)
                        .clipShape(RoundedRectangle(cornerRadius: 16))
                        .gesture(
                            DragGesture(minimumDistance: 0)
                                .onChanged { _ in if !gun.fire { gun.setHeldFire(true) } }
                                .onEnded { _ in gun.setHeldFire(false) }
                        )
                }
            }
            .navigationTitle("PoliceGun")
            .background(HiddenVolumeView().frame(width: 0, height: 0))
        }
    }
}

@main
struct PoliceGunApp: App {
    var body: some Scene {
        WindowGroup { ContentView() }
    }
}
