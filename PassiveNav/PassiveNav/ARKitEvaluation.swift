import ARKit
import Combine
import SceneKit
import SwiftUI
import UIKit

struct ARKitPoseSample: Codable, Identifiable {
    let id: UUID
    /// Seconds since ARKit session start (uptime-based normalization; legacy column `timestamp_s` in bundle CSV).
    let timestamp: TimeInterval
    /// Wall-clock seconds since Unix epoch when this frame was delivered (align with external logs, e.g. RFID).
    let unixTimestampS: TimeInterval
    let rawFrameTimestamp: TimeInterval
    let callbackUptime: TimeInterval
    let trackingState: String
    let trackingReason: String
    let transformMatrix: [Double]
    let xM: Double
    let yM: Double
    let zM: Double
    let yawRad: Double

    enum CodingKeys: String, CodingKey {
        case id, timestamp, unixTimestampS, rawFrameTimestamp, callbackUptime
        case trackingState, trackingReason, transformMatrix, xM, yM, zM, yawRad
    }

    init(
        id: UUID,
        timestamp: TimeInterval,
        unixTimestampS: TimeInterval,
        rawFrameTimestamp: TimeInterval,
        callbackUptime: TimeInterval,
        trackingState: String,
        trackingReason: String,
        transformMatrix: [Double],
        xM: Double,
        yM: Double,
        zM: Double,
        yawRad: Double
    ) {
        self.id = id
        self.timestamp = timestamp
        self.unixTimestampS = unixTimestampS
        self.rawFrameTimestamp = rawFrameTimestamp
        self.callbackUptime = callbackUptime
        self.trackingState = trackingState
        self.trackingReason = trackingReason
        self.transformMatrix = transformMatrix
        self.xM = xM
        self.yM = yM
        self.zM = zM
        self.yawRad = yawRad
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(UUID.self, forKey: .id)
        timestamp = try c.decode(TimeInterval.self, forKey: .timestamp)
        unixTimestampS = try c.decodeIfPresent(TimeInterval.self, forKey: .unixTimestampS) ?? 0
        rawFrameTimestamp = try c.decode(TimeInterval.self, forKey: .rawFrameTimestamp)
        callbackUptime = try c.decode(TimeInterval.self, forKey: .callbackUptime)
        trackingState = try c.decode(String.self, forKey: .trackingState)
        trackingReason = try c.decode(String.self, forKey: .trackingReason)
        transformMatrix = try c.decode([Double].self, forKey: .transformMatrix)
        xM = try c.decode(Double.self, forKey: .xM)
        yM = try c.decode(Double.self, forKey: .yM)
        zM = try c.decode(Double.self, forKey: .zM)
        yawRad = try c.decode(Double.self, forKey: .yawRad)
    }

    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(id, forKey: .id)
        try c.encode(timestamp, forKey: .timestamp)
        try c.encode(unixTimestampS, forKey: .unixTimestampS)
        try c.encode(rawFrameTimestamp, forKey: .rawFrameTimestamp)
        try c.encode(callbackUptime, forKey: .callbackUptime)
        try c.encode(trackingState, forKey: .trackingState)
        try c.encode(trackingReason, forKey: .trackingReason)
        try c.encode(transformMatrix, forKey: .transformMatrix)
        try c.encode(xM, forKey: .xM)
        try c.encode(yM, forKey: .yM)
        try c.encode(zM, forKey: .zM)
        try c.encode(yawRad, forKey: .yawRad)
    }
}

enum SensorEvaluationRunMode: String, Codable {
    case arkitOnly = "arkit_only"
    case imuAndARKit = "imu_arkit"

    var label: String {
        switch self {
        case .arkitOnly:
            return "ARKit only"
        case .imuAndARKit:
            return "IMU + ARKit"
        }
    }
}

struct SensorEvaluationRun: Codable, Identifiable {
    let id: UUID
    var name: String
    let mode: SensorEvaluationRunMode
    let testType: TestType?
    let startedAt: Date
    let endedAt: Date
    let sampleInterval: TimeInterval?
    let notes: String
    let timestampBasis: String
    let recordingStartUptime: TimeInterval
    let imuSamples: [IMUSample]
    let arkitFrames: [ARKitPoseSample]
}

struct ARKitPoseRecording {
    let startedAt: Date
    let endedAt: Date
    let startUptime: TimeInterval
    let frames: [ARKitPoseSample]
}

struct MotionRecorderStopResult {
    let imuRun: TestRun
    let evaluationRun: SensorEvaluationRun?
}

struct ARKitPathPoint: Identifiable, Hashable {
    let id = UUID()
    let x: Double
    let y: Double
}

final class ARKitPoseRecorder: NSObject, ObservableObject, ARSessionDelegate {
    @Published private(set) var isRecording = false
    @Published private(set) var elapsedSeconds: TimeInterval = 0
    @Published private(set) var frameCount = 0
    @Published private(set) var trackingState = "Idle"
    @Published private(set) var trackingReason = ""
    @Published private(set) var statusMessage = ""
    @Published private(set) var previewPoints: [ARKitPathPoint] = []

    private let session = ARSession()
    private let latestPoseLock = NSLock()
    private var latestPoseForSampling: ARKitPoseSample?
    private var managesIdleTimer = true
    private var startedAt: Date?
    private var startUptime: TimeInterval?
    private var timer: Timer?
    private var frames: [ARKitPoseSample] = []

    var previewSession: ARSession {
        session
    }

    /// - Parameter manageIdleTimer: When embedded in another recorder (e.g. PassiveNav), pass `false` so idle timer is only counted once.
    func start(startedAt: Date = Date(), startUptime: TimeInterval = ProcessInfo.processInfo.systemUptime, manageIdleTimer: Bool = true) -> Bool {
        guard !isRecording else { return true }
        guard ARWorldTrackingConfiguration.isSupported else {
            statusMessage = "ARKit world tracking is not supported on this device."
            trackingState = "Unsupported"
            return false
        }

        self.startedAt = startedAt
        self.startUptime = startUptime
        self.frames = []
        self.previewPoints = []
        self.frameCount = 0
        self.elapsedSeconds = 0
        self.trackingState = "Starting"
        self.trackingReason = ""
        self.statusMessage = ""
        self.managesIdleTimer = manageIdleTimer
        self.isRecording = true
        if manageIdleTimer {
            RecordingIdleTimer.beginRecording()
        }

        latestPoseLock.lock()
        latestPoseForSampling = nil
        latestPoseLock.unlock()

        session.delegate = self
        let configuration = ARWorldTrackingConfiguration()
        configuration.worldAlignment = .gravity
        session.run(configuration, options: [.resetTracking, .removeExistingAnchors])

        timer = Timer.scheduledTimer(withTimeInterval: 0.2, repeats: true) { [weak self] _ in
            guard let self, let startedAt = self.startedAt else { return }
            self.elapsedSeconds = Date().timeIntervalSince(startedAt)
        }
        return true
    }

    func stop() -> ARKitPoseRecording? {
        guard isRecording, let startedAt, let startUptime else { return nil }
        let endedAt = Date()
        session.pause()
        session.delegate = nil
        timer?.invalidate()
        timer = nil
        isRecording = false
        if managesIdleTimer {
            RecordingIdleTimer.endRecording()
        }
        latestPoseLock.lock()
        latestPoseForSampling = nil
        latestPoseLock.unlock()
        frameCount = frames.count

        return ARKitPoseRecording(
            startedAt: startedAt,
            endedAt: endedAt,
            startUptime: startUptime,
            frames: frames
        )
    }

    /// Latest ARKit camera pose for cross-sensor sampling (thread-safe). Timestamps are seconds since `startUptime` passed to `start`.
    func latestARKitSnapshot() -> ARKitPoseSample? {
        latestPoseLock.lock()
        defer { latestPoseLock.unlock() }
        return latestPoseForSampling
    }

    func session(_ session: ARSession, didUpdate frame: ARFrame) {
        let callbackUptime = ProcessInfo.processInfo.systemUptime
        let rawTimestamp = frame.timestamp
        let start = startUptime ?? callbackUptime
        let timestamp = Self.normalizedTimestamp(
            rawFrameTimestamp: rawTimestamp,
            callbackUptime: callbackUptime,
            startUptime: start
        )
        let transform = frame.camera.transform
        let tracking = Self.trackingLabels(for: frame.camera.trackingState)
        let unixTs = Date().timeIntervalSince1970
        let sample = ARKitPoseSample(
            id: UUID(),
            timestamp: timestamp,
            unixTimestampS: unixTs,
            rawFrameTimestamp: rawTimestamp,
            callbackUptime: callbackUptime,
            trackingState: tracking.state,
            trackingReason: tracking.reason,
            transformMatrix: Self.rowMajorMatrix(transform),
            xM: Double(transform.columns.3.x),
            yM: Double(transform.columns.3.y),
            zM: Double(transform.columns.3.z),
            yawRad: Self.yawRadians(from: transform)
        )

        latestPoseLock.lock()
        latestPoseForSampling = sample
        latestPoseLock.unlock()

        DispatchQueue.main.async { [weak self] in
            guard let self, self.isRecording else { return }
            self.frames.append(sample)
            self.frameCount = self.frames.count
            self.trackingState = tracking.state
            self.trackingReason = tracking.reason

            if self.frameCount % 5 == 0 {
                self.previewPoints = Self.pathPoints(from: self.frames)
            }
        }
    }

    static func normalizedTimestamp(
        rawFrameTimestamp: TimeInterval,
        callbackUptime: TimeInterval,
        startUptime: TimeInterval
    ) -> TimeInterval {
        let rawLooksLikeUptime = rawFrameTimestamp > startUptime - 10 && rawFrameTimestamp < callbackUptime + 10
        let value = rawLooksLikeUptime ? rawFrameTimestamp - startUptime : callbackUptime - startUptime
        return max(0, value)
    }

    static func pathPoints(from samples: [ARKitPoseSample]) -> [ARKitPathPoint] {
        samples.map { ARKitPathPoint(x: $0.xM, y: -$0.zM) }
    }

    /// Horizontal (XZ plane) path length in meters from projected ARKit points.
    static func pathDistanceMeters(points: [ARKitPathPoint]) -> Double? {
        guard points.count > 1 else { return nil }
        var distance = 0.0
        for index in 1..<points.count {
            distance += hypot(points[index].x - points[index - 1].x, points[index].y - points[index - 1].y)
        }
        return distance
    }

    static func yawRadians(from transform: simd_float4x4) -> Double {
        let forwardX = -Double(transform.columns.2.x)
        let forwardZ = -Double(transform.columns.2.z)
        return atan2(-forwardZ, forwardX)
    }

    static func rowMajorMatrix(_ transform: simd_float4x4) -> [Double] {
        [
            Double(transform.columns.0.x), Double(transform.columns.1.x), Double(transform.columns.2.x), Double(transform.columns.3.x),
            Double(transform.columns.0.y), Double(transform.columns.1.y), Double(transform.columns.2.y), Double(transform.columns.3.y),
            Double(transform.columns.0.z), Double(transform.columns.1.z), Double(transform.columns.2.z), Double(transform.columns.3.z),
            Double(transform.columns.0.w), Double(transform.columns.1.w), Double(transform.columns.2.w), Double(transform.columns.3.w)
        ]
    }

    static func trackingLabels(for state: ARCamera.TrackingState) -> (state: String, reason: String) {
        switch state {
        case .normal:
            return ("normal", "")
        case .notAvailable:
            return ("not_available", "")
        case .limited(let reason):
            return ("limited", limitedReasonLabel(reason))
        @unknown default:
            return ("unknown", "")
        }
    }

    private static func limitedReasonLabel(_ reason: ARCamera.TrackingState.Reason) -> String {
        switch reason {
        case .initializing:
            return "initializing"
        case .excessiveMotion:
            return "excessive_motion"
        case .insufficientFeatures:
            return "insufficient_features"
        case .relocalizing:
            return "relocalizing"
        @unknown default:
            return "unknown"
        }
    }
}

@MainActor
final class ARKitEvaluationRunStore: ObservableObject {
    @Published var runs: [SensorEvaluationRun] = []

    private let folderURL: URL
    private let encoder = JSONEncoder()
    private let decoder = JSONDecoder()

    init() {
        let base = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first!
        folderURL = base.appendingPathComponent("ARKitEvaluationRuns", isDirectory: true)
        if !FileManager.default.fileExists(atPath: folderURL.path) {
            try? FileManager.default.createDirectory(at: folderURL, withIntermediateDirectories: true)
        }
        loadRuns()
    }

    func loadRuns() {
        do {
            let files = try FileManager.default.contentsOfDirectory(
                at: folderURL,
                includingPropertiesForKeys: [.contentModificationDateKey],
                options: [.skipsHiddenFiles]
            )
            let jsonFiles = files.filter { $0.pathExtension.lowercased() == "json" }
            runs = try jsonFiles.compactMap { url in
                let data = try Data(contentsOf: url)
                return try decoder.decode(SensorEvaluationRun.self, from: data)
            }.sorted(by: { $0.startedAt > $1.startedAt })
        } catch {
            print("ARKit evaluation load failed: \(error)")
        }
    }

    func saveRun(_ run: SensorEvaluationRun) {
        do {
            encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
            let data = try encoder.encode(run)
            try data.write(to: fileURL(for: run.id), options: .atomic)
            runs.insert(run, at: 0)
        } catch {
            print("ARKit evaluation save failed: \(error)")
        }
    }

    func deleteRuns(at offsets: IndexSet) {
        for index in offsets {
            let run = runs[index]
            try? FileManager.default.removeItem(at: fileURL(for: run.id))
        }
        runs.remove(atOffsets: offsets)
    }

    func exportURLs(for run: SensorEvaluationRun) -> [URL] {
        let safeName = run.name
            .replacingOccurrences(of: " ", with: "_")
            .replacingOccurrences(of: "/", with: "-")
        let stem = "\(safeName)_\(run.id.uuidString.prefix(8))"
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent(stem, isDirectory: true)

        do {
            try? FileManager.default.removeItem(at: folder)
            try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)

            let metadataURL = folder.appendingPathComponent("metadata.json")
            let arkitURL = folder.appendingPathComponent("arkit.csv")
            let imuURL = folder.appendingPathComponent("imu.csv")

            encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
            try encoder.encode(metadata(for: run)).write(to: metadataURL, options: .atomic)
            try arkitCSV(for: run).write(to: arkitURL, atomically: true, encoding: .utf8)

            var urls = [metadataURL, arkitURL]
            if !run.imuSamples.isEmpty {
                try imuCSV(for: run).write(to: imuURL, atomically: true, encoding: .utf8)
                urls.append(imuURL)
            }
            return urls
        } catch {
            print("ARKit evaluation export failed: \(error)")
            return []
        }
    }

    private func fileURL(for id: UUID) -> URL {
        folderURL.appendingPathComponent("\(id.uuidString).json")
    }

    private func metadata(for run: SensorEvaluationRun) -> ARKitBundleMetadata {
        ARKitBundleMetadata(
            id: run.id.uuidString,
            name: run.name,
            mode: run.mode.rawValue,
            testType: run.testType?.rawValue,
            startedAt: Self.isoFormatter.string(from: run.startedAt),
            endedAt: Self.isoFormatter.string(from: run.endedAt),
            durationS: run.endedAt.timeIntervalSince(run.startedAt),
            sampleIntervalS: run.sampleInterval,
            notes: run.notes,
            timestampBasis: run.timestampBasis,
            recordingStartUptimeS: run.recordingStartUptime,
            imuSampleCount: run.imuSamples.count,
            arkitFrameCount: run.arkitFrames.count
        )
    }

    private func arkitCSV(for run: SensorEvaluationRun) -> String {
        var lines = [
            "unix_timestamp_s,timestamp_s,raw_frame_timestamp_s,callback_uptime_s,tracking_state,tracking_reason,x_m,y_m,z_m,yaw_rad,m00,m01,m02,m03,m10,m11,m12,m13,m20,m21,m22,m23,m30,m31,m32,m33"
        ]

        for frame in run.arkitFrames {
            let matrixValues = frame.transformMatrix.map(\.arkitCSVValue)
            lines.append(
                ([
                    frame.unixTimestampS.arkitCSVValue,
                    frame.timestamp.arkitCSVValue,
                    frame.rawFrameTimestamp.arkitCSVValue,
                    frame.callbackUptime.arkitCSVValue,
                    frame.trackingState.arkitCSVString,
                    frame.trackingReason.arkitCSVString,
                    frame.xM.arkitCSVValue,
                    frame.yM.arkitCSVValue,
                    frame.zM.arkitCSVValue,
                    frame.yawRad.arkitCSVValue
                ] + matrixValues).joined(separator: ",")
            )
        }
        return lines.joined(separator: "\n")
    }

    private func imuCSV(for run: SensorEvaluationRun) -> String {
        var lines = [
            "# run_name,\(run.name.replacingOccurrences(of: ",", with: ";"))",
            "# test_type,\(run.testType?.rawValue ?? "")",
            "# sample_interval,\(run.sampleInterval?.arkitCSVValue ?? "")",
            "# started_at,\(run.startedAt.timeIntervalSince1970.arkitCSVValue)",
            "# ended_at,\(run.endedAt.timeIntervalSince1970.arkitCSVValue)",
            "# notes,\(run.notes.replacingOccurrences(of: ",", with: ";"))",
            "timestamp_s,gyro_x,gyro_y,gyro_z,accel_x,accel_y,accel_z,user_accel_x,user_accel_y,user_accel_z,gravity_x,gravity_y,gravity_z,roll,pitch,yaw,mag_x,mag_y,mag_z,mag_accuracy"
        ]

        for sample in run.imuSamples {
            lines.append(
                [
                    sample.timestamp.arkitCSVValue,
                    sample.gyroX.arkitCSVValue,
                    sample.gyroY.arkitCSVValue,
                    sample.gyroZ.arkitCSVValue,
                    sample.accelX.arkitCSVValue,
                    sample.accelY.arkitCSVValue,
                    sample.accelZ.arkitCSVValue,
                    sample.userAccelX.arkitCSVValue,
                    sample.userAccelY.arkitCSVValue,
                    sample.userAccelZ.arkitCSVValue,
                    sample.gravityX.arkitCSVValue,
                    sample.gravityY.arkitCSVValue,
                    sample.gravityZ.arkitCSVValue,
                    sample.roll.arkitCSVValue,
                    sample.pitch.arkitCSVValue,
                    sample.yaw.arkitCSVValue,
                    sample.magneticFieldX.arkitCSVValue,
                    sample.magneticFieldY.arkitCSVValue,
                    sample.magneticFieldZ.arkitCSVValue,
                    sample.magneticFieldAccuracy.arkitCSVValue
                ].joined(separator: ",")
            )
        }
        return lines.joined(separator: "\n")
    }

    private static let isoFormatter: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter
    }()
}

struct ARKitBundleMetadata: Codable {
    let id: String
    let name: String
    let mode: String
    let testType: String?
    let startedAt: String
    let endedAt: String
    let durationS: Double
    let sampleIntervalS: Double?
    let notes: String
    let timestampBasis: String
    let recordingStartUptimeS: Double
    let imuSampleCount: Int
    let arkitFrameCount: Int
}

struct ARKitTabView: View {
    @ObservedObject var store: ARKitEvaluationRunStore
    @StateObject private var recorder = ARKitPoseRecorder()

    @State private var runName = ""
    @State private var notes = ""
    @State private var selectedRunID: UUID?
    @State private var shareURLs: [URL] = []

    private var selectedRun: SensorEvaluationRun? {
        store.runs.first(where: { $0.id == selectedRunID }) ?? store.runs.first
    }

    private var previewPoints: [ARKitPathPoint] {
        if recorder.isRecording {
            return recorder.previewPoints
        }
        return selectedRun.map { ARKitPoseRecorder.pathPoints(from: $0.arkitFrames) } ?? []
    }

    var body: some View {
        NavigationStack {
            List {
                Section("Recorder") {
                    TextField("Run name (optional)", text: $runName)
                        .disabled(recorder.isRecording)
                    TextField("Notes", text: $notes, axis: .vertical)
                        .disabled(recorder.isRecording)

                    Button(recorder.isRecording ? "Stop ARKit Run" : "Start ARKit Run") {
                        if recorder.isRecording {
                            stopAndSave()
                        } else {
                            _ = recorder.start()
                        }
                    }
                    .foregroundStyle(recorder.isRecording ? .red : .blue)

                    metricRow("Status", recorder.trackingState)
                    if !recorder.trackingReason.isEmpty {
                        metricRow("Reason", recorder.trackingReason)
                    }
                    metricRow("Elapsed", String(format: "%.1f s", recorder.elapsedSeconds))
                    metricRow("ARKit frames", "\(recorder.frameCount)")

                    if !recorder.statusMessage.isEmpty {
                        Text(recorder.statusMessage)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }

                Section("Camera Preview") {
                    ZStack {
                        ARKitCameraPreviewView(session: recorder.previewSession)
                            .frame(height: 280)
                            .clipShape(RoundedRectangle(cornerRadius: 8))

                        if !recorder.isRecording {
                            Text("Start ARKit Run to preview camera")
                                .font(.caption)
                                .padding(8)
                                .background(.thinMaterial)
                                .clipShape(RoundedRectangle(cornerRadius: 8))
                        }
                    }
                }

                Section("Path Preview") {
                    ARKitTopDownPathView(points: previewPoints)
                        .frame(height: 220)
                    if let distance = pathDistance(points: previewPoints) {
                        metricRow("Distance", String(format: "%.2f m", distance))
                    }
                }

                if let selectedRun {
                    Section("Export") {
                        Button {
                            shareURLs = store.exportURLs(for: selectedRun)
                        } label: {
                            Label("Export Selected ARKit Bundle", systemImage: "square.and.arrow.up")
                        }

                        Text(selectedRun.imuSamples.isEmpty ? "Exports metadata.json and arkit.csv." : "Exports metadata.json, arkit.csv, and imu.csv.")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }

                Section("Saved Evaluation Runs") {
                    if store.runs.isEmpty {
                        Text("No ARKit runs yet.")
                            .foregroundStyle(.secondary)
                    } else {
                        ForEach(store.runs) { run in
                            VStack(alignment: .leading, spacing: 8) {
                                Button {
                                    selectedRunID = run.id
                                } label: {
                                    HStack {
                                        VStack(alignment: .leading, spacing: 2) {
                                            Text(run.name)
                                            Text("\(run.mode.label) • \(run.arkitFrames.count) ARKit frames")
                                                .font(.caption)
                                                .foregroundStyle(.secondary)
                                        }
                                        Spacer()
                                        if selectedRunID == run.id || (selectedRunID == nil && store.runs.first?.id == run.id) {
                                            Image(systemName: "checkmark.circle.fill")
                                                .foregroundStyle(.blue)
                                        }
                                    }
                                }

                                Button {
                                    shareURLs = store.exportURLs(for: run)
                                } label: {
                                    Label("Export Bundle", systemImage: "square.and.arrow.up")
                                }
                                .buttonStyle(.borderless)
                            }
                            .swipeActions(edge: .trailing) {
                                Button("Export") {
                                    shareURLs = store.exportURLs(for: run)
                                }
                                .tint(.green)
                            }
                        }
                        .onDelete(perform: store.deleteRuns)
                    }
                }
            }
            .navigationTitle("ARKit")
            .sheet(isPresented: Binding(
                get: { !shareURLs.isEmpty },
                set: { if !$0 { shareURLs = [] } }
            )) {
                ARKitShareSheetView(items: shareURLs)
            }
            .onAppear {
                if selectedRunID == nil {
                    selectedRunID = store.runs.first?.id
                }
            }
        }
    }

    private func stopAndSave() {
        guard let recording = recorder.stop() else { return }
        let trimmedName = runName.trimmingCharacters(in: .whitespacesAndNewlines)
        let finalName = trimmedName.isEmpty ? "ARKit \(Self.nameFormatter.string(from: recording.startedAt))" : trimmedName
        let run = SensorEvaluationRun(
            id: UUID(),
            name: finalName,
            mode: .arkitOnly,
            testType: nil,
            startedAt: recording.startedAt,
            endedAt: recording.endedAt,
            sampleInterval: nil,
            notes: notes,
            timestampBasis: "process_uptime_seconds",
            recordingStartUptime: recording.startUptime,
            imuSamples: [],
            arkitFrames: recording.frames
        )
        store.saveRun(run)
        selectedRunID = run.id
        runName = ""
        notes = ""
    }

    @ViewBuilder
    private func metricRow(_ label: String, _ value: String) -> some View {
        HStack {
            Text(label)
            Spacer()
            Text(value)
                .foregroundStyle(.secondary)
                .monospacedDigit()
        }
    }

    private func pathDistance(points: [ARKitPathPoint]) -> Double? {
        ARKitPoseRecorder.pathDistanceMeters(points: points)
    }

    private static let nameFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd_HH-mm-ss"
        return formatter
    }()
}

struct ARKitCameraPreviewView: UIViewRepresentable {
    let session: ARSession

    func makeUIView(context: Context) -> ARSCNView {
        let view = ARSCNView(frame: .zero)
        view.session = session
        view.scene = SCNScene()
        view.automaticallyUpdatesLighting = true
        view.contentMode = .scaleAspectFill
        return view
    }

    func updateUIView(_ view: ARSCNView, context: Context) {
        if view.session !== session {
            view.session = session
        }
    }
}

struct ARKitTopDownPathView: View {
    let points: [ARKitPathPoint]

    var body: some View {
        GeometryReader { proxy in
            ZStack {
                Color(.secondarySystemBackground)
                if points.count > 1 {
                    Path { path in
                        let projected = project(points: points, size: proxy.size)
                        guard let first = projected.first else { return }
                        path.move(to: first)
                        for point in projected.dropFirst() {
                            path.addLine(to: point)
                        }
                    }
                    .stroke(.blue, lineWidth: 2)

                    let projected = project(points: points, size: proxy.size)
                    if let first = projected.first {
                        Circle()
                            .fill(.green)
                            .frame(width: 10, height: 10)
                            .position(first)
                    }
                    if let last = projected.last {
                        Circle()
                            .fill(.red)
                            .frame(width: 10, height: 10)
                            .position(last)
                    }
                } else {
                    Text("No path yet")
                        .foregroundStyle(.secondary)
                }
            }
            .clipShape(RoundedRectangle(cornerRadius: 8))
        }
    }

    private func project(points: [ARKitPathPoint], size: CGSize) -> [CGPoint] {
        guard let minX = points.map(\.x).min(),
              let maxX = points.map(\.x).max(),
              let minY = points.map(\.y).min(),
              let maxY = points.map(\.y).max() else {
            return []
        }

        let padding = 18.0
        let width = max(maxX - minX, 0.5)
        let height = max(maxY - minY, 0.5)
        let scale = min((size.width - padding * 2) / width, (size.height - padding * 2) / height)
        let centerX = (minX + maxX) / 2
        let centerY = (minY + maxY) / 2

        return points.map { point in
            CGPoint(
                x: size.width / 2 + (point.x - centerX) * scale,
                y: size.height / 2 - (point.y - centerY) * scale
            )
        }
    }
}

private struct ARKitShareSheetView: UIViewControllerRepresentable {
    let items: [URL]

    func makeUIViewController(context: Context) -> UIActivityViewController {
        UIActivityViewController(activityItems: items, applicationActivities: nil)
    }

    func updateUIViewController(_ uiViewController: UIActivityViewController, context: Context) {}
}

private extension Optional where Wrapped == Double {
    var arkitCSVValue: String {
        switch self {
        case .some(let value):
            return value.arkitCSVValue
        case .none:
            return ""
        }
    }
}

private extension Double {
    var arkitCSVValue: String {
        String(self)
    }
}

private extension String {
    var arkitCSVString: String {
        if contains(",") || contains("\"") || contains("\n") {
            return "\"\(replacingOccurrences(of: "\"", with: "\"\""))\""
        }
        return self
    }
}
