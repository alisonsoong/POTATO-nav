import SwiftUI
import CoreMotion
import Combine

struct PassiveNavIMUSample: Codable, Identifiable {
    let id: UUID
    /// Wall-clock sample time, `Date().timeIntervalSince1970` (seconds since 1970-01-01 UTC); primary key for RFID / external sensor alignment.
    let unixTimestampS: TimeInterval
    /// Core Motion `CMDeviceMotion.timestamp` (device sensor clock; not Unix time).
    let timestamp: TimeInterval
    /// Seconds since the run’s `startedAt` (`Date`).
    let elapsedSinceRunStartS: Double

    // Device motion (fused) — user acceleration & gravity
    let userAccelX: Double
    let userAccelY: Double
    let userAccelZ: Double

    let gravityX: Double
    let gravityY: Double
    let gravityZ: Double

    let fusedAccelX: Double
    let fusedAccelY: Double
    let fusedAccelZ: Double

    let gyroX: Double
    let gyroY: Double
    let gyroZ: Double

    let roll: Double
    let pitch: Double
    let yaw: Double

    let magneticFieldX: Double
    let magneticFieldY: Double
    let magneticFieldZ: Double
    let magneticFieldAccuracy: Double

    /// Raw accelerometer (includes gravity), `CMAccelerometerData` — not attitude-corrected.
    let rawAccelX: Double
    let rawAccelY: Double
    let rawAccelZ: Double

    /// Raw gyroscope (rad/s), `CMGyroData`.
    let rawGyroX: Double
    let rawGyroY: Double
    let rawGyroZ: Double

    /// Latest ARKit camera translation (m) and yaw at this sample; values repeat between ARKit frames.
    let arkitXM: Double
    let arkitYM: Double
    let arkitZM: Double
    let arkitYawRad: Double
    let arkitTimestampS: Double
    /// Unix time of the ARKit frame this row snapshots (`ARKitPoseSample.unixTimestampS`); 0 if no pose yet.
    let arkitUnixTimestampS: TimeInterval
    let arkitTrackingState: String
    let arkitTrackingReason: String

    enum CodingKeys: String, CodingKey {
        case id, unixTimestampS, timestamp, elapsedSinceRunStartS, userAccelX, userAccelY, userAccelZ
        case gravityX, gravityY, gravityZ, fusedAccelX, fusedAccelY, fusedAccelZ
        case gyroX, gyroY, gyroZ, roll, pitch, yaw
        case magneticFieldX, magneticFieldY, magneticFieldZ, magneticFieldAccuracy
        case rawAccelX, rawAccelY, rawAccelZ, rawGyroX, rawGyroY, rawGyroZ
        case arkitXM, arkitYM, arkitZM, arkitYawRad, arkitTimestampS, arkitUnixTimestampS, arkitTrackingState, arkitTrackingReason
    }

    init(
        id: UUID,
        unixTimestampS: TimeInterval,
        timestamp: TimeInterval,
        elapsedSinceRunStartS: Double,
        userAccelX: Double,
        userAccelY: Double,
        userAccelZ: Double,
        gravityX: Double,
        gravityY: Double,
        gravityZ: Double,
        fusedAccelX: Double,
        fusedAccelY: Double,
        fusedAccelZ: Double,
        gyroX: Double,
        gyroY: Double,
        gyroZ: Double,
        roll: Double,
        pitch: Double,
        yaw: Double,
        magneticFieldX: Double,
        magneticFieldY: Double,
        magneticFieldZ: Double,
        magneticFieldAccuracy: Double,
        rawAccelX: Double,
        rawAccelY: Double,
        rawAccelZ: Double,
        rawGyroX: Double,
        rawGyroY: Double,
        rawGyroZ: Double,
        arkitXM: Double,
        arkitYM: Double,
        arkitZM: Double,
        arkitYawRad: Double,
        arkitTimestampS: Double,
        arkitUnixTimestampS: TimeInterval,
        arkitTrackingState: String,
        arkitTrackingReason: String
    ) {
        self.id = id
        self.unixTimestampS = unixTimestampS
        self.timestamp = timestamp
        self.elapsedSinceRunStartS = elapsedSinceRunStartS
        self.userAccelX = userAccelX
        self.userAccelY = userAccelY
        self.userAccelZ = userAccelZ
        self.gravityX = gravityX
        self.gravityY = gravityY
        self.gravityZ = gravityZ
        self.fusedAccelX = fusedAccelX
        self.fusedAccelY = fusedAccelY
        self.fusedAccelZ = fusedAccelZ
        self.gyroX = gyroX
        self.gyroY = gyroY
        self.gyroZ = gyroZ
        self.roll = roll
        self.pitch = pitch
        self.yaw = yaw
        self.magneticFieldX = magneticFieldX
        self.magneticFieldY = magneticFieldY
        self.magneticFieldZ = magneticFieldZ
        self.magneticFieldAccuracy = magneticFieldAccuracy
        self.rawAccelX = rawAccelX
        self.rawAccelY = rawAccelY
        self.rawAccelZ = rawAccelZ
        self.rawGyroX = rawGyroX
        self.rawGyroY = rawGyroY
        self.rawGyroZ = rawGyroZ
        self.arkitXM = arkitXM
        self.arkitYM = arkitYM
        self.arkitZM = arkitZM
        self.arkitYawRad = arkitYawRad
        self.arkitTimestampS = arkitTimestampS
        self.arkitUnixTimestampS = arkitUnixTimestampS
        self.arkitTrackingState = arkitTrackingState
        self.arkitTrackingReason = arkitTrackingReason
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(UUID.self, forKey: .id)
        unixTimestampS = try c.decodeIfPresent(TimeInterval.self, forKey: .unixTimestampS) ?? 0
        timestamp = try c.decode(TimeInterval.self, forKey: .timestamp)
        elapsedSinceRunStartS = try c.decodeIfPresent(TimeInterval.self, forKey: .elapsedSinceRunStartS) ?? 0
        userAccelX = try c.decode(Double.self, forKey: .userAccelX)
        userAccelY = try c.decode(Double.self, forKey: .userAccelY)
        userAccelZ = try c.decode(Double.self, forKey: .userAccelZ)
        gravityX = try c.decode(Double.self, forKey: .gravityX)
        gravityY = try c.decode(Double.self, forKey: .gravityY)
        gravityZ = try c.decode(Double.self, forKey: .gravityZ)
        fusedAccelX = try c.decode(Double.self, forKey: .fusedAccelX)
        fusedAccelY = try c.decode(Double.self, forKey: .fusedAccelY)
        fusedAccelZ = try c.decode(Double.self, forKey: .fusedAccelZ)
        gyroX = try c.decode(Double.self, forKey: .gyroX)
        gyroY = try c.decode(Double.self, forKey: .gyroY)
        gyroZ = try c.decode(Double.self, forKey: .gyroZ)
        roll = try c.decode(Double.self, forKey: .roll)
        pitch = try c.decode(Double.self, forKey: .pitch)
        yaw = try c.decode(Double.self, forKey: .yaw)
        magneticFieldX = try c.decode(Double.self, forKey: .magneticFieldX)
        magneticFieldY = try c.decode(Double.self, forKey: .magneticFieldY)
        magneticFieldZ = try c.decode(Double.self, forKey: .magneticFieldZ)
        magneticFieldAccuracy = try c.decode(Double.self, forKey: .magneticFieldAccuracy)
        rawAccelX = try c.decodeIfPresent(Double.self, forKey: .rawAccelX) ?? 0
        rawAccelY = try c.decodeIfPresent(Double.self, forKey: .rawAccelY) ?? 0
        rawAccelZ = try c.decodeIfPresent(Double.self, forKey: .rawAccelZ) ?? 0
        rawGyroX = try c.decodeIfPresent(Double.self, forKey: .rawGyroX) ?? 0
        rawGyroY = try c.decodeIfPresent(Double.self, forKey: .rawGyroY) ?? 0
        rawGyroZ = try c.decodeIfPresent(Double.self, forKey: .rawGyroZ) ?? 0
        arkitXM = try c.decodeIfPresent(Double.self, forKey: .arkitXM) ?? 0
        arkitYM = try c.decodeIfPresent(Double.self, forKey: .arkitYM) ?? 0
        arkitZM = try c.decodeIfPresent(Double.self, forKey: .arkitZM) ?? 0
        arkitYawRad = try c.decodeIfPresent(Double.self, forKey: .arkitYawRad) ?? 0
        arkitTimestampS = try c.decodeIfPresent(Double.self, forKey: .arkitTimestampS) ?? 0
        arkitUnixTimestampS = try c.decodeIfPresent(TimeInterval.self, forKey: .arkitUnixTimestampS) ?? 0
        arkitTrackingState = try c.decodeIfPresent(String.self, forKey: .arkitTrackingState) ?? ""
        arkitTrackingReason = try c.decodeIfPresent(String.self, forKey: .arkitTrackingReason) ?? ""
    }
}

struct PassiveNavRun: Codable, Identifiable {
    let id: UUID
    var name: String
    let startedAt: Date
    let endedAt: Date
    let sampleInterval: TimeInterval
    let samples: [PassiveNavIMUSample]
    /// Native-rate ARKit camera poses (same schema as evaluation tab `arkit.csv`).
    let arkitFrames: [ARKitPoseSample]

    enum CodingKeys: String, CodingKey {
        case id, name, startedAt, endedAt, sampleInterval, samples, arkitFrames
    }

    init(id: UUID, name: String, startedAt: Date, endedAt: Date, sampleInterval: TimeInterval, samples: [PassiveNavIMUSample], arkitFrames: [ARKitPoseSample] = []) {
        self.id = id
        self.name = name
        self.startedAt = startedAt
        self.endedAt = endedAt
        self.sampleInterval = sampleInterval
        self.samples = samples
        self.arkitFrames = arkitFrames
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(UUID.self, forKey: .id)
        name = try c.decode(String.self, forKey: .name)
        startedAt = try c.decode(Date.self, forKey: .startedAt)
        endedAt = try c.decode(Date.self, forKey: .endedAt)
        sampleInterval = try c.decode(TimeInterval.self, forKey: .sampleInterval)
        samples = try c.decode([PassiveNavIMUSample].self, forKey: .samples)
        arkitFrames = try c.decodeIfPresent([ARKitPoseSample].self, forKey: .arkitFrames) ?? []
    }
}

@MainActor
final class PassiveNavRunStore: ObservableObject {
    @Published var runs: [PassiveNavRun] = []

    private let folderURL: URL
    private let encoder = JSONEncoder()
    private let decoder = JSONDecoder()

    init() {
        let base = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first!
        folderURL = base.appendingPathComponent("PassiveNavRuns", isDirectory: true)
        if !FileManager.default.fileExists(atPath: folderURL.path) {
            try? FileManager.default.createDirectory(at: folderURL, withIntermediateDirectories: true)
        }
        loadRuns()
    }

    func loadRuns() {
        do {
            let files = try FileManager.default.contentsOfDirectory(at: folderURL, includingPropertiesForKeys: nil)
            let jsonFiles = files.filter { $0.pathExtension.lowercased() == "json" }
            runs = try jsonFiles.compactMap { url in
                let data = try Data(contentsOf: url)
                return try decoder.decode(PassiveNavRun.self, from: data)
            }.sorted(by: { $0.startedAt > $1.startedAt })
        } catch {
            print("PassiveNav load failed: \(error)")
        }
    }

    func save(_ run: PassiveNavRun) {
        do {
            encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
            let data = try encoder.encode(run)
            try data.write(to: fileURL(for: run.id), options: .atomic)
            runs.insert(run, at: 0)
        } catch {
            print("PassiveNav save failed: \(error)")
        }
    }

    func rename(runID: UUID, newName: String) {
        guard let index = runs.firstIndex(where: { $0.id == runID }) else { return }
        runs[index].name = newName
        do {
            encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
            let data = try encoder.encode(runs[index])
            try data.write(to: fileURL(for: runID), options: .atomic)
        } catch {
            print("PassiveNav rename failed: \(error)")
        }
    }

    func delete(at offsets: IndexSet) {
        for index in offsets {
            let run = runs[index]
            try? FileManager.default.removeItem(at: fileURL(for: run.id))
        }
        runs.remove(atOffsets: offsets)
    }

    func exportURLs(for run: PassiveNavRun) -> [URL] {
        let safe = run.name.replacingOccurrences(of: " ", with: "_")
        let stem = "\(safe)_\(run.id.uuidString.prefix(8))"
        let temp = FileManager.default.temporaryDirectory
        let jsonURL = temp.appendingPathComponent("\(stem).json")
        let imuCSV = temp.appendingPathComponent("\(stem)_imu.csv")
        let arkitCSVURL = temp.appendingPathComponent("\(stem)_arkit.csv")

        do {
            encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
            try encoder.encode(run).write(to: jsonURL, options: .atomic)

            let imuHeader = [
                "unix_timestamp_s",
                "cm_motion_timestamp_s",
                "elapsed_since_run_start_s",
                "user_accel_x", "user_accel_y", "user_accel_z",
                "gravity_x", "gravity_y", "gravity_z",
                "fused_accel_x", "fused_accel_y", "fused_accel_z",
                "gyro_x", "gyro_y", "gyro_z",
                "roll", "pitch", "yaw",
                "mag_x", "mag_y", "mag_z", "mag_accuracy",
                "raw_accel_x", "raw_accel_y", "raw_accel_z",
                "raw_gyro_x", "raw_gyro_y", "raw_gyro_z",
                "arkit_x_m", "arkit_y_m", "arkit_z_m", "arkit_yaw_rad", "arkit_timestamp_s", "arkit_unix_timestamp_s",
                "arkit_tracking_state", "arkit_tracking_reason"
            ].joined(separator: ",")

            var imuLines = [imuHeader]
            for s in run.samples {
                imuLines.append(
                    [
                        "\(s.unixTimestampS)", "\(s.timestamp)", "\(s.elapsedSinceRunStartS)",
                        "\(s.userAccelX)", "\(s.userAccelY)", "\(s.userAccelZ)",
                        "\(s.gravityX)", "\(s.gravityY)", "\(s.gravityZ)",
                        "\(s.fusedAccelX)", "\(s.fusedAccelY)", "\(s.fusedAccelZ)",
                        "\(s.gyroX)", "\(s.gyroY)", "\(s.gyroZ)",
                        "\(s.roll)", "\(s.pitch)", "\(s.yaw)",
                        "\(s.magneticFieldX)", "\(s.magneticFieldY)", "\(s.magneticFieldZ)", "\(s.magneticFieldAccuracy)",
                        "\(s.rawAccelX)", "\(s.rawAccelY)", "\(s.rawAccelZ)",
                        "\(s.rawGyroX)", "\(s.rawGyroY)", "\(s.rawGyroZ)",
                        "\(s.arkitXM)", "\(s.arkitYM)", "\(s.arkitZM)", "\(s.arkitYawRad)", "\(s.arkitTimestampS)", "\(s.arkitUnixTimestampS)",
                        passiveNavCSVField(s.arkitTrackingState),
                        passiveNavCSVField(s.arkitTrackingReason)
                    ].joined(separator: ",")
                )
            }
            try imuLines.joined(separator: "\n").write(to: imuCSV, atomically: true, encoding: .utf8)

            var urls: [URL] = [jsonURL, imuCSV]
            if !run.arkitFrames.isEmpty {
                var arkitLines = [
                    "unix_timestamp_s,timestamp_s,raw_frame_timestamp_s,callback_uptime_s,tracking_state,tracking_reason,x_m,y_m,z_m,yaw_rad,m00,m01,m02,m03,m10,m11,m12,m13,m20,m21,m22,m23,m30,m31,m32,m33"
                ]
                for frame in run.arkitFrames {
                    let matrixValues = frame.transformMatrix.map { String($0) }
                    arkitLines.append(
                        ([
                            String(frame.unixTimestampS),
                            String(frame.timestamp),
                            String(frame.rawFrameTimestamp),
                            String(frame.callbackUptime),
                            passiveNavCSVField(frame.trackingState),
                            passiveNavCSVField(frame.trackingReason),
                            String(frame.xM),
                            String(frame.yM),
                            String(frame.zM),
                            String(frame.yawRad)
                        ] + matrixValues).joined(separator: ",")
                    )
                }
                try arkitLines.joined(separator: "\n").write(to: arkitCSVURL, atomically: true, encoding: .utf8)
                urls.append(arkitCSVURL)
            }
            return urls
        } catch {
            print("PassiveNav export failed: \(error)")
            return []
        }
    }

    private func fileURL(for id: UUID) -> URL {
        folderURL.appendingPathComponent("\(id.uuidString).json")
    }
}

private func passiveNavCSVField(_ s: String) -> String {
    if s.contains(",") || s.contains("\"") || s.contains("\n") {
        return "\"" + s.replacingOccurrences(of: "\"", with: "\"\"") + "\""
    }
    return s
}

private func passiveNavPathDistance(points: [ARKitPathPoint]) -> Double? {
    ARKitPoseRecorder.pathDistanceMeters(points: points)
}

@MainActor
final class PassiveNavRecorder: ObservableObject {
    @Published private(set) var isRecording = false
    @Published private(set) var elapsed: TimeInterval = 0
    @Published private(set) var sampleCount = 0
    @Published private(set) var arKitStarted = false

    private let motionManager = CMMotionManager()
    private let embeddedARKitPoseRecorder = ARKitPoseRecorder()
    private let queue = OperationQueue()
    private let motionInterval: TimeInterval = 1.0 / 50.0
    private var startedAt: Date?
    private var timer: Timer?
    private var runName: String = ""
    private var samples: [PassiveNavIMUSample] = []
    private var arKitForwardCancellable: AnyCancellable?

    /// Shared AR session for PassiveNav (path preview and logging). No camera preview UI required.
    var arKitPoseRecorder: ARKitPoseRecorder { embeddedARKitPoseRecorder }

    func start(name: String) {
        guard !isRecording else { return }
        guard motionManager.isDeviceMotionAvailable else { return }

        runName = name
        let recordStartedAt = Date()
        let startUptime = ProcessInfo.processInfo.systemUptime
        startedAt = recordStartedAt
        isRecording = true
        arKitStarted = embeddedARKitPoseRecorder.start(startedAt: recordStartedAt, startUptime: startUptime, manageIdleTimer: false)
        arKitForwardCancellable = embeddedARKitPoseRecorder.objectWillChange
            .receive(on: DispatchQueue.main)
            .sink { [weak self] _ in
                self?.objectWillChange.send()
            }
        RecordingIdleTimer.beginRecording()
        elapsed = 0
        sampleCount = 0
        samples = []

        queue.maxConcurrentOperationCount = 1

        if motionManager.isAccelerometerAvailable {
            motionManager.accelerometerUpdateInterval = motionInterval
            motionManager.startAccelerometerUpdates()
        }
        if motionManager.isGyroAvailable {
            motionManager.gyroUpdateInterval = motionInterval
            motionManager.startGyroUpdates()
        }

        motionManager.deviceMotionUpdateInterval = motionInterval
        motionManager.startDeviceMotionUpdates(using: .xArbitraryCorrectedZVertical, to: queue) { [weak self] motion, _ in
            guard let self, let motion, let startedAt = self.startedAt else { return }

            let unixTs = Date().timeIntervalSince1970
            let t = motion.timestamp
            let elapsedRun = Date().timeIntervalSince(startedAt)

            let rawA = self.motionManager.accelerometerData?.acceleration
            let rawAx = Double(rawA?.x ?? 0)
            let rawAy = Double(rawA?.y ?? 0)
            let rawAz = Double(rawA?.z ?? 0)

            let rawG = self.motionManager.gyroData?.rotationRate
            let rawGx = Double(rawG?.x ?? 0)
            let rawGy = Double(rawG?.y ?? 0)
            let rawGz = Double(rawG?.z ?? 0)

            let userAx = motion.userAcceleration.x
            let userAy = motion.userAcceleration.y
            let userAz = motion.userAcceleration.z

            let gravX = motion.gravity.x
            let gravY = motion.gravity.y
            let gravZ = motion.gravity.z

            let fusedX = userAx + gravX
            let fusedY = userAy + gravY
            let fusedZ = userAz + gravZ

            let gX = motion.rotationRate.x
            let gY = motion.rotationRate.y
            let gZ = motion.rotationRate.z

            let roll = motion.attitude.roll
            let pitch = motion.attitude.pitch
            let yaw = motion.attitude.yaw

            let magField = motion.magneticField.field
            let magX = magField.x
            let magY = magField.y
            let magZ = magField.z
            let magAcc = motion.magneticField.accuracy.rawValue

            let ar = self.embeddedARKitPoseRecorder.latestARKitSnapshot()
            let arkitXM = ar.map { $0.xM } ?? 0
            let arkitYM = ar.map { $0.yM } ?? 0
            let arkitZM = ar.map { $0.zM } ?? 0
            let arkitYawRad = ar.map { $0.yawRad } ?? 0
            let arkitTimestampS = ar.map { $0.timestamp } ?? 0
            let arkitUnixTimestampS = ar?.unixTimestampS ?? 0
            let arkitTrackingState = ar?.trackingState ?? (self.arKitStarted ? "none_yet" : "not_running")
            let arkitTrackingReason = ar?.trackingReason ?? ""

            let sample = PassiveNavIMUSample(
                id: UUID(),
                unixTimestampS: unixTs,
                timestamp: t,
                elapsedSinceRunStartS: elapsedRun,
                userAccelX: userAx,
                userAccelY: userAy,
                userAccelZ: userAz,
                gravityX: gravX,
                gravityY: gravY,
                gravityZ: gravZ,
                fusedAccelX: fusedX,
                fusedAccelY: fusedY,
                fusedAccelZ: fusedZ,
                gyroX: gX,
                gyroY: gY,
                gyroZ: gZ,
                roll: roll,
                pitch: pitch,
                yaw: yaw,
                magneticFieldX: magX,
                magneticFieldY: magY,
                magneticFieldZ: magZ,
                magneticFieldAccuracy: Double(magAcc),
                rawAccelX: rawAx,
                rawAccelY: rawAy,
                rawAccelZ: rawAz,
                rawGyroX: rawGx,
                rawGyroY: rawGy,
                rawGyroZ: rawGz,
                arkitXM: arkitXM,
                arkitYM: arkitYM,
                arkitZM: arkitZM,
                arkitYawRad: arkitYawRad,
                arkitTimestampS: arkitTimestampS,
                arkitUnixTimestampS: arkitUnixTimestampS,
                arkitTrackingState: arkitTrackingState,
                arkitTrackingReason: arkitTrackingReason
            )

            Task { @MainActor [weak self] in
                guard let self else { return }
                self.samples.append(sample)
                self.sampleCount = self.samples.count

                if self.sampleCount % 50 == 0 {
                    print("PassiveNav sample",
                          "t:", t,
                          "userAccel:", userAx, userAy, userAz,
                          "gravity:", gravX, gravY, gravZ,
                          "gyro:", gX, gY, gZ,
                          "rpy:", roll, pitch, yaw,
                          "mag:", magX, magY, magZ,
                          "magAcc:", magAcc,
                          "rawAccel:", rawAx, rawAy, rawAz,
                          "rawGyro:", rawGx, rawGy, rawGz,
                          "arkit:", arkitXM, arkitYM, arkitZM)
                }
            }
        }

        let elapsedAnchor = recordStartedAt
        timer = Timer.scheduledTimer(withTimeInterval: 0.2, repeats: true) { [weak self] _ in
            DispatchQueue.main.async { @MainActor [weak self] in
                guard let self else { return }
                self.elapsed = Date().timeIntervalSince(elapsedAnchor)
            }
        }
    }

    func stop() -> PassiveNavRun? {
        guard isRecording, let startedAt else { return nil }
        motionManager.stopDeviceMotionUpdates()
        motionManager.stopAccelerometerUpdates()
        motionManager.stopGyroUpdates()
        arKitForwardCancellable?.cancel()
        arKitForwardCancellable = nil
        let arkitRecording = embeddedARKitPoseRecorder.stop()
        timer?.invalidate()
        timer = nil
        isRecording = false
        arKitStarted = false
        RecordingIdleTimer.endRecording()
        sampleCount = samples.count
        let endedAt = Date()

        let trimmed = runName.trimmingCharacters(in: .whitespacesAndNewlines)
        let finalName = trimmed.isEmpty ? "Run \(Self.nameFormatter.string(from: startedAt))" : trimmed

        return PassiveNavRun(
            id: UUID(),
            name: finalName,
            startedAt: startedAt,
            endedAt: endedAt,
            sampleInterval: motionInterval,
            samples: samples,
            arkitFrames: arkitRecording?.frames ?? []
        )
    }

    private static let nameFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd HH:mm:ss"
        return formatter
    }()
}

struct PassiveNavTabView: View {
    @StateObject private var recorder = PassiveNavRecorder()
    @StateObject private var store = PassiveNavRunStore()

    @State private var runNameDraft = ""
    @State private var selectedRunID: UUID?
    @State private var shareURLs: [URL] = []
    @State private var renameDraft = ""
    @State private var showRenameAlert = false

    private var pathPreviewPoints: [ARKitPathPoint] {
        if recorder.isRecording {
            return recorder.arKitPoseRecorder.previewPoints
        }
        guard let run = store.runs.first(where: { $0.id == selectedRunID }) ?? store.runs.first else {
            return []
        }
        return ARKitPoseRecorder.pathPoints(from: run.arkitFrames)
    }

    var body: some View {
        NavigationStack {
            List {
                Section {
                    TextField("Run name (optional)", text: $runNameDraft)
                        .disabled(recorder.isRecording)

                    Button(recorder.isRecording ? "Stop Run" : "Start Run") {
                        if recorder.isRecording {
                            if let run = recorder.stop() {
                                store.save(run)
                                selectedRunID = run.id
                                runNameDraft = ""
                            }
                        } else {
                            recorder.start(name: runNameDraft)
                        }
                    }
                    .foregroundStyle(recorder.isRecording ? .red : .blue)

                    HStack {
                        Text("Elapsed")
                        Spacer()
                        Text(String(format: "%.1f s", recorder.elapsed))
                            .monospacedDigit()
                    }

                    HStack {
                        Text("IMU samples")
                        Spacer()
                        Text("\(recorder.sampleCount)")
                            .monospacedDigit()
                    }
                } header: {
                    Text("Recorder")
                } footer: {
                    Text("Timestamps in exports are Unix epoch seconds for alignment with external sensors. See PASSIVE_NAV_CSV_GUIDE.md in the PassiveNav folder for column definitions.")
                }

                Section {
                    ARKitTopDownPathView(points: pathPreviewPoints)
                        .frame(height: 200)
                        .listRowInsets(EdgeInsets(top: 8, leading: 16, bottom: 8, trailing: 16))
                    if let distance = passiveNavPathDistance(points: pathPreviewPoints) {
                        HStack {
                            Text("Horizontal path length")
                            Spacer()
                            Text(String(format: "%.2f m", distance))
                                .foregroundStyle(.secondary)
                                .monospacedDigit()
                        }
                    }
                } header: {
                    Text("ARKit path (top-down)")
                } footer: {
                    Text("Plan view: horizontal X vs −Z. Green = start, red = latest. No camera preview; ARKit still uses the camera for tracking.")
                        .font(.caption)
                }

                Section("Saved Runs") {
                    if store.runs.isEmpty {
                        Text("No runs yet.")
                            .foregroundStyle(.secondary)
                    } else {
                        ForEach(store.runs) { run in
                            Button {
                                selectedRunID = run.id
                            } label: {
                                HStack {
                                    VStack(alignment: .leading, spacing: 2) {
                                        Text(run.name)
                                        Text("\(run.samples.count) IMU • \(run.arkitFrames.count) ARKit frames")
                                            .font(.caption)
                                            .foregroundStyle(.secondary)
                                    }
                                    Spacer()
                                    if selectedRunID == run.id {
                                        Image(systemName: "checkmark.circle.fill")
                                            .foregroundStyle(.blue)
                                    }
                                }
                            }
                            .swipeActions(edge: .trailing) {
                                Button("Rename") {
                                    renameDraft = run.name
                                    selectedRunID = run.id
                                    showRenameAlert = true
                                }
                                .tint(.orange)

                                Button("Export") {
                                    shareURLs = store.exportURLs(for: run)
                                }
                                .tint(.green)
                            }
                        }
                        .onDelete(perform: store.delete)
                    }
                }
            }
            .navigationTitle("PassiveNav")
            .sheet(isPresented: Binding(
                get: { !shareURLs.isEmpty },
                set: { if !$0 { shareURLs = [] } }
            )) {
                ShareSheetView(items: shareURLs)
            }
            .alert("Rename run", isPresented: $showRenameAlert) {
                TextField("Run name", text: $renameDraft)
                Button("Cancel", role: .cancel) {}
                Button("Save") {
                    guard let runID = selectedRunID else { return }
                    let trimmed = renameDraft.trimmingCharacters(in: .whitespacesAndNewlines)
                    if !trimmed.isEmpty {
                        store.rename(runID: runID, newName: trimmed)
                    }
                }
            } message: {
                Text("Update the run name shown in your saved runs list.")
            }
            .onAppear {
                if selectedRunID == nil {
                    selectedRunID = store.runs.first?.id
                }
            }
        }
    }
}

private struct ShareSheetView: UIViewControllerRepresentable {
    let items: [URL]

    func makeUIViewController(context: Context) -> UIActivityViewController {
        UIActivityViewController(activityItems: items, applicationActivities: nil)
    }

    func updateUIViewController(_ uiViewController: UIActivityViewController, context: Context) {}
}
