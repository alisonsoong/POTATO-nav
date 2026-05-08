import SwiftUI
import ARKit
import CoreMotion
import Combine
import UniformTypeIdentifiers
import UIKit
#if canImport(Charts)
import Charts
#endif

enum RecordingIdleTimer {
    private static var activeRecorders = 0

    static func beginRecording() {
        activeRecorders += 1
        UIApplication.shared.isIdleTimerDisabled = true
    }

    static func endRecording() {
        activeRecorders = max(0, activeRecorders - 1)
        UIApplication.shared.isIdleTimerDisabled = activeRecorders > 0
    }
}

enum TestType: String, CaseIterable, Codable, Identifiable {
    case staticRest = "Static Rest"
    case integration = "Integration Drift"
    case knownMotion = "Known Motion"
    case closedLoop = "Closed Loop"

    var id: String { rawValue }

    var instructions: String {
        switch self {
        case .staticRest:
            return """
            Setup:
            - Place phone flat on a stable surface and do not touch it.
            - Keep environment steady (no bumps, no vibration).

            Recording:
            - Record at least 10 minutes (20-30 minutes preferred).

            Goal:
            - Estimate static bias, noise floor, and Allan deviation from stationary data.
            """
        case .integration:
            return """
            Setup:
            - Keep phone completely still (same setup as Static Rest).

            Recording:
            - Record 5-15 minutes continuously.

            Goal:
            - Integrate gyro over time to measure orientation drift (deg/sec and deg/min).
            """
        case .knownMotion:
            return """
            Setup:
            - Stand in one spot in your room.
            - Hold the phone upright in front of your chest.
            - Use this exact sequence for one run:
              1) Face forward for 2 seconds.
              2) Rotate your body + phone about 90 degrees to the right.
              3) Hold for 2 seconds.
              4) Rotate back to your original direction.
              5) Hold for 2 seconds.
            - Keep motion speed and endpoint angles as consistent as possible.

            Recording:
            - Recommended: Start recording at step 1 and stop after step 5 (one sequence = one run).
            - Repeat 10-30 runs.

            Goal:
            - Measure angular error accumulation and trial-to-trial variation.
            """
        case .closedLoop:
            return """
            Setup:
            - Mark a small square in your room (about 3 ft x 3 ft) with tape or visual markers.
            - Choose one corner as the exact start/end point.
            - Hold/carry the phone the same way every run.
            - Walk the square at steady pace: 4 straight segments with 90 degree turns.

            Recording:
            - Recommended: Start at the start corner, walk exactly one full loop, stop at the same corner (one loop = one run).
            - Repeat 5-15 runs with similar pacing.

            Goal:
            - Measure end-to-end dead-reckoning drift using endpoint error.
            """
        }
    }
}

struct IMUSample: Codable, Identifiable {
    let id: UUID
    let timestamp: TimeInterval
    let gyroX: Double
    let gyroY: Double
    let gyroZ: Double
    let accelX: Double
    let accelY: Double
    let accelZ: Double
    let userAccelX: Double?
    let userAccelY: Double?
    let userAccelZ: Double?
    let gravityX: Double?
    let gravityY: Double?
    let gravityZ: Double?
    let roll: Double?
    let pitch: Double?
    let yaw: Double?
    let magneticFieldX: Double?
    let magneticFieldY: Double?
    let magneticFieldZ: Double?
    let magneticFieldAccuracy: Double?

    init(
        id: UUID,
        timestamp: TimeInterval,
        gyroX: Double,
        gyroY: Double,
        gyroZ: Double,
        accelX: Double,
        accelY: Double,
        accelZ: Double,
        userAccelX: Double? = nil,
        userAccelY: Double? = nil,
        userAccelZ: Double? = nil,
        gravityX: Double? = nil,
        gravityY: Double? = nil,
        gravityZ: Double? = nil,
        roll: Double? = nil,
        pitch: Double? = nil,
        yaw: Double? = nil,
        magneticFieldX: Double? = nil,
        magneticFieldY: Double? = nil,
        magneticFieldZ: Double? = nil,
        magneticFieldAccuracy: Double? = nil
    ) {
        self.id = id
        self.timestamp = timestamp
        self.gyroX = gyroX
        self.gyroY = gyroY
        self.gyroZ = gyroZ
        self.accelX = accelX
        self.accelY = accelY
        self.accelZ = accelZ
        self.userAccelX = userAccelX
        self.userAccelY = userAccelY
        self.userAccelZ = userAccelZ
        self.gravityX = gravityX
        self.gravityY = gravityY
        self.gravityZ = gravityZ
        self.roll = roll
        self.pitch = pitch
        self.yaw = yaw
        self.magneticFieldX = magneticFieldX
        self.magneticFieldY = magneticFieldY
        self.magneticFieldZ = magneticFieldZ
        self.magneticFieldAccuracy = magneticFieldAccuracy
    }

    enum CodingKeys: String, CodingKey {
        case id
        case timestamp
        case gyroX
        case gyroY
        case gyroZ
        case accelX
        case accelY
        case accelZ
        case userAccelX
        case userAccelY
        case userAccelZ
        case gravityX
        case gravityY
        case gravityZ
        case roll
        case pitch
        case yaw
        case magneticFieldX
        case magneticFieldY
        case magneticFieldZ
        case magneticFieldAccuracy
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decode(UUID.self, forKey: .id)
        timestamp = try container.decode(TimeInterval.self, forKey: .timestamp)
        gyroX = try container.decode(Double.self, forKey: .gyroX)
        gyroY = try container.decode(Double.self, forKey: .gyroY)
        gyroZ = try container.decode(Double.self, forKey: .gyroZ)
        accelX = try container.decode(Double.self, forKey: .accelX)
        accelY = try container.decode(Double.self, forKey: .accelY)
        accelZ = try container.decode(Double.self, forKey: .accelZ)
        userAccelX = try container.decodeIfPresent(Double.self, forKey: .userAccelX)
        userAccelY = try container.decodeIfPresent(Double.self, forKey: .userAccelY)
        userAccelZ = try container.decodeIfPresent(Double.self, forKey: .userAccelZ)
        gravityX = try container.decodeIfPresent(Double.self, forKey: .gravityX)
        gravityY = try container.decodeIfPresent(Double.self, forKey: .gravityY)
        gravityZ = try container.decodeIfPresent(Double.self, forKey: .gravityZ)
        roll = try container.decodeIfPresent(Double.self, forKey: .roll)
        pitch = try container.decodeIfPresent(Double.self, forKey: .pitch)
        yaw = try container.decodeIfPresent(Double.self, forKey: .yaw)
        magneticFieldX = try container.decodeIfPresent(Double.self, forKey: .magneticFieldX)
        magneticFieldY = try container.decodeIfPresent(Double.self, forKey: .magneticFieldY)
        magneticFieldZ = try container.decodeIfPresent(Double.self, forKey: .magneticFieldZ)
        magneticFieldAccuracy = try container.decodeIfPresent(Double.self, forKey: .magneticFieldAccuracy)
    }
}

struct TestRun: Codable, Identifiable {
    let id: UUID
    let name: String
    let type: TestType
    let startedAt: Date
    let endedAt: Date
    let sampleInterval: TimeInterval
    let notes: String
    let samples: [IMUSample]
}

struct AllanPoint: Identifiable {
    let id = UUID()
    let tau: Double
    let deviation: Double
}

struct IMUAxisStats {
    let mean: Double
    let standardDeviation: Double
}

struct IMUCharacterization {
    let gyroX: IMUAxisStats
    let gyroY: IMUAxisStats
    let gyroZ: IMUAxisStats
    let accelX: IMUAxisStats
    let accelY: IMUAxisStats
    let accelZ: IMUAxisStats
    let orientationDriftDegPerSec: Double
    let orientationDriftDegPerMin: Double
    let allanDeviationGyroZ: [AllanPoint]
    let allanDeviationAccelZ: [AllanPoint]
}

struct ParticleSimulationParameters: Codable {
    let sampleRateHz: Double
    let gyroBiasRadPerSec: Double
    let accelBiasG: Double
    let gyroNoiseDensityRadPerSecPerSqrtHz: Double
    let accelNoiseDensityGPerSqrtHz: Double
    let arwDegPerSqrtHour: Double
    let vrwMpsPerSqrtHour: Double
    let gyroBiasInstabilityDegPerHour: Double
    let accelBiasInstabilityG: Double
}

final class RunStore: ObservableObject {
    @Published var runs: [TestRun] = []
    @Published var characterizationRunIDs: Set<UUID> = []

    private let folderURL: URL
    private let encoder = JSONEncoder()
    private let decoder = JSONDecoder()
    private let characterizationDefaultsKey = "characterization_run_ids"

    init() {
        let base = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first!
        folderURL = base.appendingPathComponent("IMURuns", isDirectory: true)
        createFolderIfNeeded()
        loadRuns()
        loadCharacterizationSelection()
    }

    func loadRuns() {
        do {
            let files = try FileManager.default.contentsOfDirectory(
                at: folderURL,
                includingPropertiesForKeys: [.contentModificationDateKey],
                options: [.skipsHiddenFiles]
            )
            let jsonFiles = files.filter { $0.pathExtension.lowercased() == "json" }
            let decodedRuns = try jsonFiles.compactMap { url in
                let data = try Data(contentsOf: url)
                return try decoder.decode(TestRun.self, from: data)
            }
            runs = decodedRuns.sorted(by: { $0.startedAt > $1.startedAt })
        } catch {
            print("Failed to load runs: \(error)")
        }
    }

    func saveRun(_ run: TestRun) {
        let fileURL = folderURL.appendingPathComponent("\(run.id.uuidString).json")
        do {
            encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
            let data = try encoder.encode(run)
            try data.write(to: fileURL, options: .atomic)
            runs.insert(run, at: 0)
            characterizationRunIDs.insert(run.id)
            persistCharacterizationSelection()
        } catch {
            print("Failed to save run: \(error)")
        }
    }

    func deleteRuns(at offsets: IndexSet) {
        for index in offsets {
            let run = runs[index]
            let fileURL = folderURL.appendingPathComponent("\(run.id.uuidString).json")
            try? FileManager.default.removeItem(at: fileURL)
            characterizationRunIDs.remove(run.id)
        }
        runs.remove(atOffsets: offsets)
        persistCharacterizationSelection()
    }

    func csvURL(for run: TestRun) -> URL? {
        let temporary = FileManager.default.temporaryDirectory
        let safeName = run.name.replacingOccurrences(of: " ", with: "_")
        let fileURL = temporary.appendingPathComponent("\(safeName)_\(run.id.uuidString).csv")
        var lines: [String] = []
        lines.append("# run_name,\(run.name)")
        lines.append("# test_type,\(run.type.rawValue)")
        lines.append("# sample_interval,\(run.sampleInterval)")
        lines.append("# started_at,\(run.startedAt.timeIntervalSince1970)")
        lines.append("# ended_at,\(run.endedAt.timeIntervalSince1970)")
        lines.append("# notes,\(run.notes.replacingOccurrences(of: ",", with: ";"))")
        lines.append("timestamp,gyro_x,gyro_y,gyro_z,accel_x,accel_y,accel_z,user_accel_x,user_accel_y,user_accel_z,gravity_x,gravity_y,gravity_z,roll,pitch,yaw,mag_x,mag_y,mag_z,mag_accuracy")
        for sample in run.samples {
            lines.append(
                [
                    sample.timestamp.formattedCSVValue,
                    sample.gyroX.formattedCSVValue,
                    sample.gyroY.formattedCSVValue,
                    sample.gyroZ.formattedCSVValue,
                    sample.accelX.formattedCSVValue,
                    sample.accelY.formattedCSVValue,
                    sample.accelZ.formattedCSVValue,
                    sample.userAccelX.formattedCSVValue,
                    sample.userAccelY.formattedCSVValue,
                    sample.userAccelZ.formattedCSVValue,
                    sample.gravityX.formattedCSVValue,
                    sample.gravityY.formattedCSVValue,
                    sample.gravityZ.formattedCSVValue,
                    sample.roll.formattedCSVValue,
                    sample.pitch.formattedCSVValue,
                    sample.yaw.formattedCSVValue,
                    sample.magneticFieldX.formattedCSVValue,
                    sample.magneticFieldY.formattedCSVValue,
                    sample.magneticFieldZ.formattedCSVValue,
                    sample.magneticFieldAccuracy.formattedCSVValue
                ].joined(separator: ",")
            )
        }
        do {
            try lines.joined(separator: "\n").write(to: fileURL, atomically: true, encoding: .utf8)
            return fileURL
        } catch {
            print("Failed to export csv: \(error)")
            return nil
        }
    }

    private func createFolderIfNeeded() {
        if !FileManager.default.fileExists(atPath: folderURL.path) {
            try? FileManager.default.createDirectory(at: folderURL, withIntermediateDirectories: true)
        }
    }

    private func loadCharacterizationSelection() {
        let stored = UserDefaults.standard.stringArray(forKey: characterizationDefaultsKey) ?? []
        let parsed = Set(stored.compactMap(UUID.init(uuidString:)))
        if stored.isEmpty {
            characterizationRunIDs = Set(runs.map(\.id))
            persistCharacterizationSelection()
        } else {
            characterizationRunIDs = parsed.intersection(Set(runs.map(\.id)))
            persistCharacterizationSelection()
        }
    }

    private func persistCharacterizationSelection() {
        let value = characterizationRunIDs.map(\.uuidString)
        UserDefaults.standard.set(value, forKey: characterizationDefaultsKey)
    }

    func isRunSelectedForCharacterization(_ runID: UUID) -> Bool {
        characterizationRunIDs.contains(runID)
    }

    func setRun(_ runID: UUID, selectedForCharacterization selected: Bool) {
        if selected {
            characterizationRunIDs.insert(runID)
        } else {
            characterizationRunIDs.remove(runID)
        }
        persistCharacterizationSelection()
    }

    func selectedRuns() -> [TestRun] {
        runs.filter { characterizationRunIDs.contains($0.id) }
    }

    func importRunFromCSV(url: URL, fallbackType: TestType, fallbackName: String?) throws {
        let text = try String(contentsOf: url, encoding: .utf8)
        let rawLines = text.components(separatedBy: .newlines).filter { !$0.trimmingCharacters(in: .whitespaces).isEmpty }

        var metadata: [String: String] = [:]
        var dataLines: [String] = []
        for line in rawLines {
            if line.hasPrefix("#") {
                let withoutHash = line.dropFirst().trimmingCharacters(in: .whitespaces)
                let parts = withoutHash.split(separator: ",", maxSplits: 1).map(String.init)
                if parts.count == 2 {
                    metadata[parts[0].trimmingCharacters(in: .whitespaces)] = parts[1].trimmingCharacters(in: .whitespaces)
                }
            } else {
                dataLines.append(line)
            }
        }

        guard !dataLines.isEmpty else {
            throw NSError(domain: "CSVImport", code: 1, userInfo: [NSLocalizedDescriptionKey: "CSV has no sample data."])
        }

        let headerColumns = dataLines
            .removeFirst()
            .split(separator: ",", omittingEmptySubsequences: false)
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() }
        let headerIndex = Dictionary(uniqueKeysWithValues: headerColumns.enumerated().map { ($1, $0) })

        guard headerIndex["timestamp"] != nil || headerIndex["timestamp_s"] != nil,
              headerIndex["gyro_x"] != nil,
              headerIndex["accel_z"] != nil || headerIndex["fused_accel_z"] != nil else {
            throw NSError(domain: "CSVImport", code: 2, userInfo: [NSLocalizedDescriptionKey: "CSV format not recognized."])
        }

        var samples: [IMUSample] = []
        samples.reserveCapacity(dataLines.count)
        for line in dataLines {
            let cols = line.split(separator: ",", omittingEmptySubsequences: false).map(String.init)
            guard let t = csvDouble(["timestamp", "timestamp_s"], from: cols, headerIndex: headerIndex),
                  let gx = csvDouble(["gyro_x"], from: cols, headerIndex: headerIndex),
                  let gy = csvDouble(["gyro_y"], from: cols, headerIndex: headerIndex),
                  let gz = csvDouble(["gyro_z"], from: cols, headerIndex: headerIndex),
                  let ax = csvDouble(["accel_x", "fused_accel_x"], from: cols, headerIndex: headerIndex),
                  let ay = csvDouble(["accel_y", "fused_accel_y"], from: cols, headerIndex: headerIndex),
                  let az = csvDouble(["accel_z", "fused_accel_z"], from: cols, headerIndex: headerIndex) else {
                continue
            }
            samples.append(
                IMUSample(
                    id: UUID(),
                    timestamp: t,
                    gyroX: gx,
                    gyroY: gy,
                    gyroZ: gz,
                    accelX: ax,
                    accelY: ay,
                    accelZ: az,
                    userAccelX: csvDouble(["user_accel_x"], from: cols, headerIndex: headerIndex),
                    userAccelY: csvDouble(["user_accel_y"], from: cols, headerIndex: headerIndex),
                    userAccelZ: csvDouble(["user_accel_z"], from: cols, headerIndex: headerIndex),
                    gravityX: csvDouble(["gravity_x"], from: cols, headerIndex: headerIndex),
                    gravityY: csvDouble(["gravity_y"], from: cols, headerIndex: headerIndex),
                    gravityZ: csvDouble(["gravity_z"], from: cols, headerIndex: headerIndex),
                    roll: csvDouble(["roll"], from: cols, headerIndex: headerIndex),
                    pitch: csvDouble(["pitch"], from: cols, headerIndex: headerIndex),
                    yaw: csvDouble(["yaw"], from: cols, headerIndex: headerIndex),
                    magneticFieldX: csvDouble(["mag_x"], from: cols, headerIndex: headerIndex),
                    magneticFieldY: csvDouble(["mag_y"], from: cols, headerIndex: headerIndex),
                    magneticFieldZ: csvDouble(["mag_z"], from: cols, headerIndex: headerIndex),
                    magneticFieldAccuracy: csvDouble(["mag_accuracy"], from: cols, headerIndex: headerIndex)
                )
            )
        }

        guard !samples.isEmpty else {
            throw NSError(domain: "CSVImport", code: 3, userInfo: [NSLocalizedDescriptionKey: "No valid rows were found in CSV."])
        }

        let parsedType = TestType.allCases.first(where: { $0.rawValue == metadata["test_type"] }) ?? fallbackType
        let nameFromFile = fallbackName?.trimmingCharacters(in: .whitespacesAndNewlines)
        let runName = (nameFromFile?.isEmpty == false ? nameFromFile! : (metadata["run_name"] ?? url.deletingPathExtension().lastPathComponent))
        let parsedInterval = Double(metadata["sample_interval"] ?? "")
        let inferredInterval = inferSampleInterval(samples: samples)
        let sampleInterval = parsedInterval ?? inferredInterval
        let startedAt = metadata["started_at"].flatMap(Double.init).map(Date.init(timeIntervalSince1970:)) ?? Date()
        let endedAt = metadata["ended_at"].flatMap(Double.init).map(Date.init(timeIntervalSince1970:)) ?? startedAt.addingTimeInterval(samples.last?.timestamp ?? 0)
        let notes = metadata["notes"] ?? "Imported from CSV"

        let run = TestRun(
            id: UUID(),
            name: runName,
            type: parsedType,
            startedAt: startedAt,
            endedAt: endedAt,
            sampleInterval: sampleInterval,
            notes: notes,
            samples: samples
        )
        saveRun(run)
    }

    private func inferSampleInterval(samples: [IMUSample]) -> TimeInterval {
        guard samples.count > 1 else { return 0.01 }
        var diffs: [Double] = []
        diffs.reserveCapacity(samples.count - 1)
        for i in 1..<samples.count {
            let dt = samples[i].timestamp - samples[i - 1].timestamp
            if dt > 0 { diffs.append(dt) }
        }
        guard !diffs.isEmpty else { return 0.01 }
        return diffs.reduce(0, +) / Double(diffs.count)
    }

    private func csvDouble(_ keys: [String], from columns: [String], headerIndex: [String: Int]) -> Double? {
        for key in keys {
            guard let index = headerIndex[key], index < columns.count else { continue }
            let trimmed = columns[index].trimmingCharacters(in: .whitespacesAndNewlines)
            guard !trimmed.isEmpty else { return nil }
            return Double(trimmed)
        }
        return nil
    }

}

final class MotionRecorder: ObservableObject {
    @Published var isRecording = false
    @Published var elapsedSeconds: TimeInterval = 0
    @Published var sampleCount: Int = 0
    @Published var arkitFrameCount: Int = 0
    @Published var arkitTrackingState: String = "Idle"
    @Published var arkitTrackingReason: String = ""
    @Published var arkitStatusMessage: String = ""

    private let motionManager = CMMotionManager()
    private let queue = OperationQueue()
    private let arkitPoseRecorder = ARKitPoseRecorder()
    private var startedAt: Date?
    private var recordingStartUptime: TimeInterval?
    private var timer: Timer?
    private var samples: [IMUSample] = []
    private var currentType: TestType = .staticRest
    private var currentName: String = ""
    private var currentNotes: String = ""
    private var sampleInterval: TimeInterval = 0.02
    private var recordARKitGroundTruth = false

    var arkitPreviewSession: ARSession {
        arkitPoseRecorder.previewSession
    }

    var isRecordingARKitGroundTruth: Bool {
        recordARKitGroundTruth
    }

    func start(type: TestType, name: String, notes: String, sampleInterval: TimeInterval, recordARKitGroundTruth: Bool) {
        guard !isRecording else { return }
        guard motionManager.isDeviceMotionAvailable else { return }

        let startDate = Date()
        let startUptime = ProcessInfo.processInfo.systemUptime

        self.currentType = type
        self.currentName = name
        self.currentNotes = notes
        self.sampleInterval = sampleInterval
        self.recordARKitGroundTruth = false
        self.samples = []
        self.elapsedSeconds = 0
        self.sampleCount = 0
        self.arkitFrameCount = 0
        self.arkitTrackingState = "Idle"
        self.arkitTrackingReason = ""
        self.arkitStatusMessage = ""
        self.startedAt = startDate
        self.recordingStartUptime = startUptime
        self.isRecording = true
        RecordingIdleTimer.beginRecording()

        if recordARKitGroundTruth {
            self.recordARKitGroundTruth = arkitPoseRecorder.start(startedAt: startDate, startUptime: startUptime)
            if !self.recordARKitGroundTruth {
                arkitStatusMessage = arkitPoseRecorder.statusMessage
                arkitTrackingState = arkitPoseRecorder.trackingState
            }
        }

        queue.maxConcurrentOperationCount = 1
        motionManager.deviceMotionUpdateInterval = sampleInterval

        let preferredFrame: CMAttitudeReferenceFrame = CMMotionManager.availableAttitudeReferenceFrames().contains(.xArbitraryCorrectedZVertical)
            ? .xArbitraryCorrectedZVertical
            : .xArbitraryZVertical

        motionManager.startDeviceMotionUpdates(using: preferredFrame, to: queue) { [weak self] motion, _ in
            guard let self, let motion, let start = self.startedAt else { return }
            let timestamp: TimeInterval
            if self.recordARKitGroundTruth, let recordingStartUptime = self.recordingStartUptime {
                timestamp = max(0, motion.timestamp - recordingStartUptime)
            } else {
                timestamp = Date().timeIntervalSince(start)
            }
            let userAccelX = motion.userAcceleration.x
            let userAccelY = motion.userAcceleration.y
            let userAccelZ = motion.userAcceleration.z
            let gravityX = motion.gravity.x
            let gravityY = motion.gravity.y
            let gravityZ = motion.gravity.z
            let magneticField = motion.magneticField.field
            let sample = IMUSample(
                id: UUID(),
                timestamp: timestamp,
                gyroX: motion.rotationRate.x,
                gyroY: motion.rotationRate.y,
                gyroZ: motion.rotationRate.z,
                accelX: userAccelX + gravityX,
                accelY: userAccelY + gravityY,
                accelZ: userAccelZ + gravityZ,
                userAccelX: userAccelX,
                userAccelY: userAccelY,
                userAccelZ: userAccelZ,
                gravityX: gravityX,
                gravityY: gravityY,
                gravityZ: gravityZ,
                roll: motion.attitude.roll,
                pitch: motion.attitude.pitch,
                yaw: motion.attitude.yaw,
                magneticFieldX: magneticField.x,
                magneticFieldY: magneticField.y,
                magneticFieldZ: magneticField.z,
                magneticFieldAccuracy: Double(motion.magneticField.accuracy.rawValue)
            )
            self.samples.append(sample)
            if self.samples.count % 10 == 0 {
                DispatchQueue.main.async {
                    self.sampleCount = self.samples.count
                }
            }
        }

        timer = Timer.scheduledTimer(withTimeInterval: 0.2, repeats: true) { [weak self] _ in
            guard let self, let startedAt = self.startedAt else { return }
            self.elapsedSeconds = Date().timeIntervalSince(startedAt)
            if self.recordARKitGroundTruth {
                self.arkitFrameCount = self.arkitPoseRecorder.frameCount
                self.arkitTrackingState = self.arkitPoseRecorder.trackingState
                self.arkitTrackingReason = self.arkitPoseRecorder.trackingReason
                self.arkitStatusMessage = self.arkitPoseRecorder.statusMessage
            }
        }
    }

    func stop() -> MotionRecorderStopResult? {
        guard isRecording, let startedAt else { return nil }
        let end = Date()
        motionManager.stopDeviceMotionUpdates()
        let arkitRecording = recordARKitGroundTruth ? arkitPoseRecorder.stop() : nil
        timer?.invalidate()
        timer = nil
        isRecording = false
        RecordingIdleTimer.endRecording()
        sampleCount = samples.count
        arkitFrameCount = arkitRecording?.frames.count ?? arkitFrameCount

        let runName = currentName.isEmpty ? "\(currentType.rawValue) \(Self.dateFormatter.string(from: startedAt))" : currentName
        let imuRun = TestRun(
            id: UUID(),
            name: runName,
            type: currentType,
            startedAt: startedAt,
            endedAt: end,
            sampleInterval: sampleInterval,
            notes: currentNotes,
            samples: samples
        )

        let evaluationRun = arkitRecording.map { recording in
            SensorEvaluationRun(
                id: UUID(),
                name: runName,
                mode: .imuAndARKit,
                testType: currentType,
                startedAt: startedAt,
                endedAt: end,
                sampleInterval: sampleInterval,
                notes: currentNotes,
                timestampBasis: "process_uptime_seconds",
                recordingStartUptime: recording.startUptime,
                imuSamples: samples,
                arkitFrames: recording.frames
            )
        }

        recordARKitGroundTruth = false
        return MotionRecorderStopResult(imuRun: imuRun, evaluationRun: evaluationRun)
    }

    private static let dateFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd_HH-mm-ss"
        return formatter
    }()
}

private extension Optional where Wrapped == Double {
    var formattedCSVValue: String {
        switch self {
        case .some(let value):
            return value.formattedCSVValue
        case .none:
            return ""
        }
    }
}

private extension Double {
    var formattedCSVValue: String {
        String(self)
    }
}

enum Analyzer {
    static func characterize(run: TestRun) -> IMUCharacterization? {
        guard !run.samples.isEmpty else { return nil }
        let samples = run.samples

        let gyroX = axisStats(values: samples.map(\.gyroX))
        let gyroY = axisStats(values: samples.map(\.gyroY))
        let gyroZ = axisStats(values: samples.map(\.gyroZ))
        let accelX = axisStats(values: samples.map(\.accelX))
        let accelY = axisStats(values: samples.map(\.accelY))
        let accelZ = axisStats(values: samples.map(\.accelZ))
        let drift = orientationDrift(samples: samples)
        let allanGyroZ = allanDeviation(signal: samples.map(\.gyroZ), dt: run.sampleInterval)
        let allanAccelZ = allanDeviation(signal: samples.map(\.accelZ), dt: run.sampleInterval)

        return IMUCharacterization(
            gyroX: gyroX,
            gyroY: gyroY,
            gyroZ: gyroZ,
            accelX: accelX,
            accelY: accelY,
            accelZ: accelZ,
            orientationDriftDegPerSec: drift,
            orientationDriftDegPerMin: drift * 60,
            allanDeviationGyroZ: allanGyroZ,
            allanDeviationAccelZ: allanAccelZ
        )
    }

    private static func axisStats(values: [Double]) -> IMUAxisStats {
        let mean = values.reduce(0, +) / Double(values.count)
        let variance = values.reduce(0) { partial, value in
            partial + pow(value - mean, 2)
        } / Double(max(values.count - 1, 1))
        return IMUAxisStats(mean: mean, standardDeviation: sqrt(variance))
    }

    private static func orientationDrift(samples: [IMUSample]) -> Double {
        guard samples.count > 1 else { return 0 }

        var yawRad = 0.0
        for i in 1..<samples.count {
            let dt = samples[i].timestamp - samples[i - 1].timestamp
            yawRad += samples[i].gyroZ * dt
        }
        let totalTime = samples.last!.timestamp - samples.first!.timestamp
        guard totalTime > 0 else { return 0 }
        return abs(yawRad) * 180 / .pi / totalTime
    }

    private static func allanDeviation(signal: [Double], dt: TimeInterval) -> [AllanPoint] {
        let n = signal.count
        guard n > 32 else { return [] }

        var points: [AllanPoint] = []
        var cluster = 1

        while cluster * 2 < n / 2 {
            let m = n / cluster
            if m < 3 { break }

            var averages: [Double] = []
            averages.reserveCapacity(m)

            for i in 0..<m {
                let start = i * cluster
                let end = min(start + cluster, n)
                guard end > start else { continue }
                let section = signal[start..<end]
                averages.append(section.reduce(0, +) / Double(section.count))
            }

            if averages.count > 2 {
                var sum = 0.0
                for i in 0..<(averages.count - 1) {
                    sum += pow(averages[i + 1] - averages[i], 2)
                }
                let variance = 0.5 * sum / Double(averages.count - 1)
                let sigma = sqrt(max(variance, 0))
                points.append(AllanPoint(tau: Double(cluster) * dt, deviation: sigma))
            }

            cluster *= 2
        }

        return points
    }

}

struct ContentView: View {
    @StateObject private var store = RunStore()
    @StateObject private var arkitStore = ARKitEvaluationRunStore()
    @StateObject private var recorder = MotionRecorder()

    var body: some View {
        TabView {
            TestTabView(store: store, arkitStore: arkitStore, recorder: recorder)
                .tabItem {
                    Label("Tests", systemImage: "record.circle")
                }

            DataManagementTabView(store: store)
                .tabItem {
                    Label("Data", systemImage: "folder")
                }

            ResultsTabView(store: store)
                .tabItem {
                    Label("Results", systemImage: "function")
                }

            ARKitTabView(store: arkitStore)
                .tabItem {
                    Label("ARKit", systemImage: "camera.viewfinder")
                }

            PassiveNavTabView()
                .tabItem {
                    Label("PassiveNav", systemImage: "figure.walk.motion")
                }
        }
    }
}

struct TestTabView: View {
    @ObservedObject var store: RunStore
    @ObservedObject var arkitStore: ARKitEvaluationRunStore
    @ObservedObject var recorder: MotionRecorder

    @State private var selectedType: TestType = .staticRest
    @State private var runName = ""
    @State private var notes = ""
    @State private var sampleRateHz = 100.0
    @State private var recordARKitGroundTruth = false

    var body: some View {
        NavigationStack {
            Form {
                Section("Test Setup") {
                    Picker("Test Type", selection: $selectedType) {
                        ForEach(TestType.allCases) { type in
                            Text(type.rawValue).tag(type)
                        }
                    }

                    Text(selectedType.instructions)
                        .font(.footnote)
                        .foregroundStyle(.secondary)

                    TextField("Run Name (optional)", text: $runName)
                    TextField("Notes", text: $notes, axis: .vertical)

                    HStack {
                        Text("Sampling Rate")
                        Spacer()
                        Text("\(Int(sampleRateHz)) Hz")
                            .foregroundStyle(.secondary)
                    }
                    Slider(value: $sampleRateHz, in: 10...400, step: 10)
                    Text("Requested rate. Actual delivered rate may be capped by iOS/device hardware.")
                        .font(.caption)
                        .foregroundStyle(.secondary)

                    Toggle("Record ARKit ground truth", isOn: $recordARKitGroundTruth)
                        .disabled(recorder.isRecording)
                }

                Section("Recorder") {
                    HStack {
                        Text("Status")
                        Spacer()
                        Text(recorder.isRecording ? "Recording" : "Idle")
                            .foregroundStyle(recorder.isRecording ? .red : .secondary)
                    }
                    HStack {
                        Text("Elapsed")
                        Spacer()
                        Text(String(format: "%.1f s", recorder.elapsedSeconds))
                            .monospacedDigit()
                    }
                    HStack {
                        Text("Samples")
                        Spacer()
                        Text("\(recorder.sampleCount)")
                            .monospacedDigit()
                    }
                    if recordARKitGroundTruth || recorder.arkitFrameCount > 0 {
                        HStack {
                            Text("ARKit frames")
                            Spacer()
                            Text("\(recorder.arkitFrameCount)")
                                .monospacedDigit()
                        }
                        HStack {
                            Text("ARKit tracking")
                            Spacer()
                            Text(recorder.arkitTrackingReason.isEmpty ? recorder.arkitTrackingState : "\(recorder.arkitTrackingState): \(recorder.arkitTrackingReason)")
                                .foregroundStyle(.secondary)
                        }
                        if !recorder.arkitStatusMessage.isEmpty {
                            Text(recorder.arkitStatusMessage)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }

                    if recorder.isRecording {
                        Button("Stop and Save Run") {
                            if let result = recorder.stop() {
                                store.saveRun(result.imuRun)
                                if let evaluationRun = result.evaluationRun {
                                    arkitStore.saveRun(evaluationRun)
                                }
                                runName = ""
                                notes = ""
                            }
                        }
                        .foregroundStyle(.red)
                    } else {
                        Button("Start Recording") {
                            recorder.start(
                                type: selectedType,
                                name: runName,
                                notes: notes,
                                sampleInterval: 1.0 / sampleRateHz,
                                recordARKitGroundTruth: recordARKitGroundTruth
                            )
                        }
                    }
                }

                if recordARKitGroundTruth || recorder.isRecordingARKitGroundTruth || recorder.arkitFrameCount > 0 {
                    Section("ARKit Camera Preview") {
                        ZStack {
                            ARKitCameraPreviewView(session: recorder.arkitPreviewSession)
                                .frame(height: 260)
                                .clipShape(RoundedRectangle(cornerRadius: 8))

                            if !recorder.isRecordingARKitGroundTruth {
                                Text("Camera preview starts when ARKit recording starts")
                                    .font(.caption)
                                    .padding(8)
                                    .background(.thinMaterial)
                                    .clipShape(RoundedRectangle(cornerRadius: 8))
                            }
                        }
                    }
                }
            }
            .navigationTitle("Tests")
        }
    }
}

struct DataManagementTabView: View {
    @ObservedObject var store: RunStore
    @State private var selectedRunID: UUID?
    @State private var showImporter = false
    @State private var importType: TestType = .staticRest
    @State private var importName = ""
    @State private var importStatusMessage = ""

    var selectedRun: TestRun? {
        store.runs.first(where: { $0.id == selectedRunID }) ?? store.runs.first
    }

    var body: some View {
        NavigationStack {
            List {
                Section("Saved Runs") {
                    if store.runs.isEmpty {
                        Text("No saved runs yet.")
                            .foregroundStyle(.secondary)
                    } else {
                        ForEach(store.runs) { run in
                            Button {
                                selectedRunID = run.id
                            } label: {
                                HStack {
                                    VStack(alignment: .leading) {
                                        Text(run.name)
                                        Text("\(run.type.rawValue) • \(run.samples.count) samples")
                                            .font(.caption)
                                            .foregroundStyle(.secondary)
                                    }
                                    Spacer()
                                    Toggle(
                                        "Use for characterization",
                                        isOn: Binding(
                                            get: { store.isRunSelectedForCharacterization(run.id) },
                                            set: { store.setRun(run.id, selectedForCharacterization: $0) }
                                        )
                                    )
                                    .labelsHidden()
                                    if selectedRunID == run.id || (selectedRunID == nil && store.runs.first?.id == run.id) {
                                        Image(systemName: "checkmark.circle.fill")
                                            .foregroundStyle(.blue)
                                    }
                                }
                            }
                        }
                        .onDelete(perform: store.deleteRuns)
                    }
                }

                Section("Import CSV As Saved Run") {
                    Picker("Imported Run Type", selection: $importType) {
                        ForEach(TestType.allCases) { type in
                            Text(type.rawValue).tag(type)
                        }
                    }
                    TextField("Imported Run Name (optional)", text: $importName)
                    Button("Import CSV") {
                        showImporter = true
                    }
                    if !importStatusMessage.isEmpty {
                        Text(importStatusMessage)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }

                if let run = selectedRun {
                    Section("Run Details") {
                        Text("Type: \(run.type.rawValue)")
                        Text("Started: \(run.startedAt.formatted(date: .abbreviated, time: .standard))")
                        Text("Duration: \(String(format: "%.1f", run.endedAt.timeIntervalSince(run.startedAt))) s")
                        Text("Notes: \(run.notes.isEmpty ? "None" : run.notes)")

                        if let csvURL = store.csvURL(for: run) {
                            ShareLink(item: csvURL) {
                                Label("Send / Export CSV", systemImage: "square.and.arrow.up")
                            }
                        }
                    }

                    Section("Visualization (Gyro Z)") {
#if canImport(Charts)
                        Chart(Array(run.samples.prefix(400)).enumerated().map { index, sample in
                            (index: index, value: sample.gyroZ)
                        }, id: \.index) { point in
                            LineMark(
                                x: .value("Index", point.index),
                                y: .value("Gyro Z", point.value)
                            )
                        }
                        .frame(height: 180)
#else
                        Text("Charts framework unavailable on this target.")
                            .foregroundStyle(.secondary)
#endif
                    }
                }
            }
            .navigationTitle("Data Management")
            .fileImporter(
                isPresented: $showImporter,
                allowedContentTypes: [.commaSeparatedText, .plainText],
                allowsMultipleSelection: false
            ) { result in
                switch result {
                case .success(let urls):
                    guard let url = urls.first else { return }
                    do {
                        try store.importRunFromCSV(url: url, fallbackType: importType, fallbackName: importName)
                        importStatusMessage = "Imported \(url.lastPathComponent) successfully."
                        importName = ""
                    } catch {
                        importStatusMessage = "Import failed: \(error.localizedDescription)"
                    }
                case .failure(let error):
                    importStatusMessage = "Import failed: \(error.localizedDescription)"
                }
            }
        }
    }
}

struct ResultsTabView: View {
    @ObservedObject var store: RunStore

    var body: some View {
        NavigationStack {
            Form {
                Section("How Results Are Computed") {
                    Text("This page aggregates metrics across checked runs from Data Management.")
                    Text("Each section uses checked runs from its matching test type (Static Rest, Integration Drift, Known Motion, Closed Loop).")
                        .foregroundStyle(.secondary)
                }

                Section("Run Coverage") {
                    if store.runs.isEmpty {
                        Text("No saved runs yet.")
                            .foregroundStyle(.secondary)
                    } else {
                        Text("Checked runs: \(selectedRuns.count) of \(store.runs.count)")
                        typeCountRow(type: .staticRest)
                        typeCountRow(type: .integration)
                        typeCountRow(type: .knownMotion)
                        typeCountRow(type: .closedLoop)
                    }
                }

                if !selectedRuns.isEmpty {
                    Section("Share Results") {
                        if let reportURL = aggregateReportURL() {
                            ShareLink(item: reportURL) {
                                Label("Send Results Summary", systemImage: "envelope")
                            }
                        }
                        if let jsonURL = aggregateCharacterizationJSONURL() {
                            ShareLink(item: jsonURL) {
                                Label("Send JSON Characterization", systemImage: "paperplane")
                            }
                        }
                    }
                } else if !store.runs.isEmpty {
                    Section("Share Results") {
                        Text("Select at least one run in Data Management to generate characterization results.")
                            .foregroundStyle(.secondary)
                    }
                }

                if let staticSummary = staticCharacterizationSummary() {
                    Section("Static Characterization") {
                        statRow("Gyro X bias", staticSummary.gyroX.mean)
                        statRow("Gyro Y bias", staticSummary.gyroY.mean)
                        statRow("Gyro Z bias", staticSummary.gyroZ.mean)
                        statRow("Accel X bias", staticSummary.accelX.mean)
                        statRow("Accel Y bias", staticSummary.accelY.mean)
                        statRow("Accel Z bias", staticSummary.accelZ.mean)
                        statRow("Gyro Z noise", staticSummary.gyroZ.standardDeviation)
                        statRow("Accel Z noise", staticSummary.accelZ.standardDeviation)
                    }

                    Section("Allan Deviation (Static Gyro Z)") {
                        if staticSummary.allanDeviationGyroZ.isEmpty {
                            Text("Not enough static samples for Allan deviation.")
                                .foregroundStyle(.secondary)
                        } else {
#if canImport(Charts)
                            Chart(staticSummary.allanDeviationGyroZ) { point in
                                LineMark(
                                    x: .value("Tau", point.tau),
                                    y: .value("Deviation", point.deviation)
                                )
                                PointMark(
                                    x: .value("Tau", point.tau),
                                    y: .value("Deviation", point.deviation)
                                )
                            }
                            .frame(height: 220)
#else
                            ForEach(staticSummary.allanDeviationGyroZ.prefix(10)) { point in
                                HStack {
                                    Text("tau \(String(format: "%.3f", point.tau)) s")
                                    Spacer()
                                    Text("\(String(format: "%.6f", point.deviation))")
                                }
                            }
#endif
                        }
                    }

                    if let sim = particleParameters(from: staticSummary) {
                        Section("Particle Simulator Parameters") {
                            statRow("Sample rate (Hz)", sim.sampleRateHz)
                            statRow("Gyro bias z (rad/s)", sim.gyroBiasRadPerSec)
                            statRow("Accel bias z (g)", sim.accelBiasG)
                            statRow("Gyro noise density", sim.gyroNoiseDensityRadPerSecPerSqrtHz)
                            statRow("Accel noise density", sim.accelNoiseDensityGPerSqrtHz)
                            statRow("ARW (deg/sqrt(hr))", sim.arwDegPerSqrtHour)
                            statRow("VRW (m/s/sqrt(hr))", sim.vrwMpsPerSqrtHour)
                            statRow("Gyro bias instability (deg/hr)", sim.gyroBiasInstabilityDegPerHour)
                            statRow("Accel bias instability (g)", sim.accelBiasInstabilityG)
                        }
                    }
                }

                if let integration = integrationDriftSummary() {
                    Section("Integration Drift") {
                        statRow("Runs", Double(integration.count))
                        statRow("Mean deg/sec", integration.meanDegPerSec)
                        statRow("Mean deg/min", integration.meanDegPerMin)
                        statRow("Max deg/min", integration.maxDegPerMin)
                    }
                }

                if let known = knownMotionSummary() {
                    Section("Known Motion Closure") {
                        statRow("Runs", Double(known.count))
                        statRow("Mean closure error (deg)", known.meanClosureDeg)
                        statRow("Max closure error (deg)", known.maxClosureDeg)
                    }
                }

                if let loop = closedLoopSummary() {
                    Section("Closed Loop Heading Closure") {
                        statRow("Runs", Double(loop.count))
                        statRow("Mean closure error (deg)", loop.meanClosureDeg)
                        statRow("Max closure error (deg)", loop.maxClosureDeg)
                    }
                }
            }
            .navigationTitle("Results")
        }
    }

    @ViewBuilder
    private func statRow(_ label: String, _ value: Double) -> some View {
        HStack {
            Text(label)
            Spacer()
            Text(String(format: "%.6f", value))
                .monospacedDigit()
                .foregroundStyle(.secondary)
        }
    }

    @ViewBuilder
    private func typeCountRow(type: TestType) -> some View {
        HStack {
            Text(type.rawValue)
            Spacer()
            Text("\(runs(of: type).count)")
                .foregroundStyle(.secondary)
                .monospacedDigit()
        }
    }

    private func runs(of type: TestType) -> [TestRun] {
        selectedRuns.filter { $0.type == type }
    }

    private var selectedRuns: [TestRun] {
        store.selectedRuns()
    }

    private func staticCharacterizationSummary() -> IMUCharacterization? {
        let staticRuns = runs(of: .staticRest)
        guard !staticRuns.isEmpty else { return nil }
        let mergedSamples = staticRuns.flatMap(\.samples)
        guard let sampleInterval = staticRuns.first?.sampleInterval else { return nil }
        let mergedRun = TestRun(
            id: UUID(),
            name: "Merged Static Runs",
            type: .staticRest,
            startedAt: Date(),
            endedAt: Date(),
            sampleInterval: sampleInterval,
            notes: "",
            samples: mergedSamples
        )
        return Analyzer.characterize(run: mergedRun)
    }

    private func staticSampleRateHz() -> Double? {
        let staticRuns = runs(of: .staticRest)
        guard !staticRuns.isEmpty else { return nil }
        let intervals = staticRuns.map(\.sampleInterval).filter { $0 > 0 }
        guard !intervals.isEmpty else { return nil }
        let meanInterval = intervals.reduce(0, +) / Double(intervals.count)
        return meanInterval > 0 ? 1.0 / meanInterval : nil
    }

    private func particleParameters(from summary: IMUCharacterization) -> ParticleSimulationParameters? {
        guard let sampleRateHz = staticSampleRateHz(), sampleRateHz > 0 else { return nil }
        let gyroNoiseDensity = summary.gyroZ.standardDeviation / sqrt(sampleRateHz)
        let accelNoiseDensity = summary.accelZ.standardDeviation / sqrt(sampleRateHz)
        let arw = gyroNoiseDensity * 180 / .pi * sqrt(3600)
        let vrw = accelNoiseDensity * 9.80665 * sqrt(3600)
        let gyroBiasInstability = estimateBiasInstability(from: summary.allanDeviationGyroZ) * 180 / .pi * 3600
        let accelBiasInstability = estimateBiasInstability(from: summary.allanDeviationAccelZ)
        return ParticleSimulationParameters(
            sampleRateHz: sampleRateHz,
            gyroBiasRadPerSec: summary.gyroZ.mean,
            accelBiasG: summary.accelZ.mean,
            gyroNoiseDensityRadPerSecPerSqrtHz: gyroNoiseDensity,
            accelNoiseDensityGPerSqrtHz: accelNoiseDensity,
            arwDegPerSqrtHour: arw,
            vrwMpsPerSqrtHour: vrw,
            gyroBiasInstabilityDegPerHour: gyroBiasInstability,
            accelBiasInstabilityG: accelBiasInstability
        )
    }

    private func estimateBiasInstability(from allan: [AllanPoint]) -> Double {
        guard let minSigma = allan.map(\.deviation).min() else { return 0 }
        return minSigma / 0.664
    }

    private func integrationDriftSummary() -> (count: Int, meanDegPerSec: Double, meanDegPerMin: Double, maxDegPerMin: Double)? {
        let runs = runs(of: .integration)
        let drifts = runs.compactMap { run -> Double? in
            let runForAnalysis = TestRun(
                id: run.id,
                name: run.name,
                type: run.type,
                startedAt: run.startedAt,
                endedAt: run.endedAt,
                sampleInterval: run.sampleInterval,
                notes: run.notes,
                samples: run.samples
            )
            return Analyzer.characterize(run: runForAnalysis)?.orientationDriftDegPerSec
        }
        guard !drifts.isEmpty else { return nil }
        let meanSec = drifts.reduce(0, +) / Double(drifts.count)
        return (drifts.count, meanSec, meanSec * 60, (drifts.max() ?? 0) * 60)
    }

    private func knownMotionSummary() -> (count: Int, meanClosureDeg: Double, maxClosureDeg: Double)? {
        closureSummary(for: .knownMotion)
    }

    private func closedLoopSummary() -> (count: Int, meanClosureDeg: Double, maxClosureDeg: Double)? {
        closureSummary(for: .closedLoop)
    }

    private func closureSummary(for type: TestType) -> (count: Int, meanClosureDeg: Double, maxClosureDeg: Double)? {
        let targetRuns = runs(of: type)
        let errors = targetRuns.compactMap { run -> Double? in
            let samples = run.samples
            guard samples.count > 1 else { return nil }
            var yaw = 0.0
            for i in 1..<samples.count {
                yaw += samples[i].gyroZ * (samples[i].timestamp - samples[i - 1].timestamp)
            }
            return abs(yaw) * 180 / .pi
        }
        guard !errors.isEmpty else { return nil }
        return (errors.count, errors.reduce(0, +) / Double(errors.count), errors.max() ?? 0)
    }

    private func aggregateReportURL() -> URL? {
        let temporary = FileManager.default.temporaryDirectory
        let fileURL = temporary.appendingPathComponent("Results_Aggregate.txt")
        var lines = [
            "IMU Characterization Results",
            "Aggregate Across Checked Runs",
            "",
            "Checked runs: \(selectedRuns.count)",
            "Static Rest runs: \(runs(of: .staticRest).count)",
            "Integration Drift runs: \(runs(of: .integration).count)",
            "Known Motion runs: \(runs(of: .knownMotion).count)",
            "Closed Loop runs: \(runs(of: .closedLoop).count)",
            "",
        ]

        if let staticSummary = staticCharacterizationSummary() {
            lines += [
                "Static Characterization",
                "gyro_x_bias: \(String(format: "%.8f", staticSummary.gyroX.mean))",
                "gyro_y_bias: \(String(format: "%.8f", staticSummary.gyroY.mean))",
                "gyro_z_bias: \(String(format: "%.8f", staticSummary.gyroZ.mean))",
                "accel_x_bias: \(String(format: "%.8f", staticSummary.accelX.mean))",
                "accel_y_bias: \(String(format: "%.8f", staticSummary.accelY.mean))",
                "accel_z_bias: \(String(format: "%.8f", staticSummary.accelZ.mean))",
                "gyro_z_noise: \(String(format: "%.8f", staticSummary.gyroZ.standardDeviation))",
                "accel_z_noise: \(String(format: "%.8f", staticSummary.accelZ.standardDeviation))",
                ""
            ]
            if let sim = particleParameters(from: staticSummary) {
                lines += [
                    "Particle Simulator Parameters",
                    "sample_rate_hz: \(String(format: "%.8f", sim.sampleRateHz))",
                    "gyro_bias_z_rad_per_sec: \(String(format: "%.8f", sim.gyroBiasRadPerSec))",
                    "accel_bias_z_g: \(String(format: "%.8f", sim.accelBiasG))",
                    "gyro_noise_density_rad_per_sec_per_sqrt_hz: \(String(format: "%.8f", sim.gyroNoiseDensityRadPerSecPerSqrtHz))",
                    "accel_noise_density_g_per_sqrt_hz: \(String(format: "%.8f", sim.accelNoiseDensityGPerSqrtHz))",
                    "arw_deg_per_sqrt_hour: \(String(format: "%.8f", sim.arwDegPerSqrtHour))",
                    "vrw_mps_per_sqrt_hour: \(String(format: "%.8f", sim.vrwMpsPerSqrtHour))",
                    "gyro_bias_instability_deg_per_hour: \(String(format: "%.8f", sim.gyroBiasInstabilityDegPerHour))",
                    "accel_bias_instability_g: \(String(format: "%.8f", sim.accelBiasInstabilityG))",
                    ""
                ]
            }
            lines += ["Allan Deviation Gyro Z (tau_s,deviation)"]
            lines += staticSummary.allanDeviationGyroZ.map { point in
                "\(String(format: "%.8f", point.tau)),\(String(format: "%.8f", point.deviation))"
            }
            lines += ["", "Allan Deviation Accel Z (tau_s,deviation)"]
            lines += staticSummary.allanDeviationAccelZ.map { point in
                "\(String(format: "%.8f", point.tau)),\(String(format: "%.8f", point.deviation))"
            }
            lines += [""]
        }

        if let integration = integrationDriftSummary() {
            lines += [
                "Integration Drift Summary",
                "runs: \(integration.count)",
                "mean_deg_per_sec: \(String(format: "%.8f", integration.meanDegPerSec))",
                "mean_deg_per_min: \(String(format: "%.8f", integration.meanDegPerMin))",
                "max_deg_per_min: \(String(format: "%.8f", integration.maxDegPerMin))",
                ""
            ]
        }

        if let known = knownMotionSummary() {
            lines += [
                "Known Motion Closure Summary",
                "runs: \(known.count)",
                "mean_closure_error_deg: \(String(format: "%.8f", known.meanClosureDeg))",
                "max_closure_error_deg: \(String(format: "%.8f", known.maxClosureDeg))",
                ""
            ]
        }

        if let loop = closedLoopSummary() {
            lines += [
                "Closed Loop Heading Closure Summary",
                "runs: \(loop.count)",
                "mean_closure_error_deg: \(String(format: "%.8f", loop.meanClosureDeg))",
                "max_closure_error_deg: \(String(format: "%.8f", loop.maxClosureDeg))",
                ""
            ]
        }

        do {
            try lines.joined(separator: "\n").write(to: fileURL, atomically: true, encoding: .utf8)
            return fileURL
        } catch {
            print("Failed to create results report: \(error)")
            return nil
        }
    }

    private func aggregateCharacterizationJSONURL() -> URL? {
        guard let staticSummary = staticCharacterizationSummary(),
              let sim = particleParameters(from: staticSummary) else {
            return nil
        }

        let payload: [String: Any] = [
            "checked_runs": selectedRuns.count,
            "run_counts": [
                "static_rest": runs(of: .staticRest).count,
                "integration_drift": runs(of: .integration).count,
                "known_motion": runs(of: .knownMotion).count,
                "closed_loop": runs(of: .closedLoop).count
            ],
            "static_bias": [
                "gyro_x": staticSummary.gyroX.mean,
                "gyro_y": staticSummary.gyroY.mean,
                "gyro_z": staticSummary.gyroZ.mean,
                "accel_x": staticSummary.accelX.mean,
                "accel_y": staticSummary.accelY.mean,
                "accel_z": staticSummary.accelZ.mean
            ],
            "static_noise_std": [
                "gyro_x": staticSummary.gyroX.standardDeviation,
                "gyro_y": staticSummary.gyroY.standardDeviation,
                "gyro_z": staticSummary.gyroZ.standardDeviation,
                "accel_x": staticSummary.accelX.standardDeviation,
                "accel_y": staticSummary.accelY.standardDeviation,
                "accel_z": staticSummary.accelZ.standardDeviation
            ],
            "particle_parameters": [
                "sample_rate_hz": sim.sampleRateHz,
                "gyro_bias_z_rad_per_sec": sim.gyroBiasRadPerSec,
                "accel_bias_z_g": sim.accelBiasG,
                "gyro_noise_density_rad_per_sec_per_sqrt_hz": sim.gyroNoiseDensityRadPerSecPerSqrtHz,
                "accel_noise_density_g_per_sqrt_hz": sim.accelNoiseDensityGPerSqrtHz,
                "arw_deg_per_sqrt_hour": sim.arwDegPerSqrtHour,
                "vrw_mps_per_sqrt_hour": sim.vrwMpsPerSqrtHour,
                "gyro_bias_instability_deg_per_hour": sim.gyroBiasInstabilityDegPerHour,
                "accel_bias_instability_g": sim.accelBiasInstabilityG
            ]
        ]

        do {
            let data = try JSONSerialization.data(withJSONObject: payload, options: [.prettyPrinted, .sortedKeys])
            let url = FileManager.default.temporaryDirectory.appendingPathComponent("IMU_Characterization.json")
            try data.write(to: url, options: .atomic)
            return url
        } catch {
            print("Failed to create json characterization: \(error)")
            return nil
        }
    }
}

#Preview {
    ContentView()
}
