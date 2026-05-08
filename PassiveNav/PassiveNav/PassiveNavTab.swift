import SwiftUI
import CoreMotion
import Combine

struct PassiveNavIMUSample: Codable, Identifiable {
    let id: UUID
    let timestamp: TimeInterval

    // Raw components
    let userAccelX: Double
    let userAccelY: Double
    let userAccelZ: Double

    let gravityX: Double
    let gravityY: Double
    let gravityZ: Double

    // Fused acceleration = user + gravity
    let fusedAccelX: Double
    let fusedAccelY: Double
    let fusedAccelZ: Double

    // Gyroscope
    let gyroX: Double
    let gyroY: Double
    let gyroZ: Double

    // Attitude
    let roll: Double
    let pitch: Double
    let yaw: Double

    // Magnetometer (if available)
    let magneticFieldX: Double
    let magneticFieldY: Double
    let magneticFieldZ: Double
    let magneticFieldAccuracy: Double
}

struct PassiveNavRun: Codable, Identifiable {
    let id: UUID
    var name: String
    let startedAt: Date
    let endedAt: Date
    let sampleInterval: TimeInterval
    let samples: [PassiveNavIMUSample]
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

        do {
            encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
            try encoder.encode(run).write(to: jsonURL, options: .atomic)

            var imuLines = ["timestamp_s,user_accel_x,user_accel_y,user_accel_z,gravity_x,gravity_y,gravity_z,fused_accel_x,fused_accel_y,fused_accel_z,gyro_x,gyro_y,gyro_z,roll,pitch,yaw,mag_x,mag_y,mag_z,mag_accuracy"]
            for s in run.samples {
                imuLines.append(
                    "\(s.timestamp),\(s.userAccelX),\(s.userAccelY),\(s.userAccelZ),\(s.gravityX),\(s.gravityY),\(s.gravityZ),\(s.fusedAccelX),\(s.fusedAccelY),\(s.fusedAccelZ),\(s.gyroX),\(s.gyroY),\(s.gyroZ),\(s.roll),\(s.pitch),\(s.yaw),\(s.magneticFieldX),\(s.magneticFieldY),\(s.magneticFieldZ),\(s.magneticFieldAccuracy)"
                )
            }
            try imuLines.joined(separator: "\n").write(to: imuCSV, atomically: true, encoding: .utf8)
            return [jsonURL, imuCSV]
        } catch {
            print("PassiveNav export failed: \(error)")
            return []
        }
    }

    private func fileURL(for id: UUID) -> URL {
        folderURL.appendingPathComponent("\(id.uuidString).json")
    }
}

@MainActor
final class PassiveNavRecorder: ObservableObject {
    @Published private(set) var isRecording = false
    @Published private(set) var elapsed: TimeInterval = 0
    @Published private(set) var sampleCount = 0

    private let motionManager = CMMotionManager()
    private let queue = OperationQueue()
    private let motionInterval: TimeInterval = 1.0 / 50.0
    private var startedAt: Date?
    private var timer: Timer?
    private var runName: String = ""
    private var samples: [PassiveNavIMUSample] = []

    func start(name: String) {
        guard !isRecording else { return }
        guard motionManager.isDeviceMotionAvailable else { return }

        runName = name
        startedAt = Date()
        isRecording = true
        RecordingIdleTimer.beginRecording()
        elapsed = 0
        sampleCount = 0
        samples = []

        queue.maxConcurrentOperationCount = 1
        motionManager.deviceMotionUpdateInterval = motionInterval
        motionManager.startDeviceMotionUpdates(using: .xArbitraryCorrectedZVertical, to: queue) { [weak self] motion, _ in
            guard let self, let motion, let startedAt = self.startedAt else { return }

            let t = motion.timestamp

            // User acceleration & gravity
            let userAx = motion.userAcceleration.x
            let userAy = motion.userAcceleration.y
            let userAz = motion.userAcceleration.z

            let gravX = motion.gravity.x
            let gravY = motion.gravity.y
            let gravZ = motion.gravity.z

            let fusedX = userAx + gravX
            let fusedY = userAy + gravY
            let fusedZ = userAz + gravZ

            // Gyro
            let gX = motion.rotationRate.x
            let gY = motion.rotationRate.y
            let gZ = motion.rotationRate.z

            // Attitude
            let roll = motion.attitude.roll
            let pitch = motion.attitude.pitch
            let yaw = motion.attitude.yaw

            // Magnetometer (calibrated) - may be zero on unsupported devices
            let magField = motion.magneticField.field
            let magX = magField.x
            let magY = magField.y
            let magZ = magField.z
            let magAcc = motion.magneticField.accuracy.rawValue

            let sample = PassiveNavIMUSample(
                id: UUID(),
                timestamp: t,
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
                magneticFieldAccuracy: Double(magAcc)
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
                          "magAcc:", magAcc)
                }
            }
        }

        timer = Timer.scheduledTimer(withTimeInterval: 0.2, repeats: true) { [weak self] _ in
            guard let self, let startedAt = self.startedAt else { return }
            self.elapsed = Date().timeIntervalSince(startedAt)
        }
    }

    func stop() -> PassiveNavRun? {
        guard isRecording, let startedAt else { return nil }
        motionManager.stopDeviceMotionUpdates()
        timer?.invalidate()
        timer = nil
        isRecording = false
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
            samples: samples
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

    var body: some View {
        NavigationStack {
            List {
                Section("Recorder") {
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
                                        Text("\(run.samples.count) IMU samples")
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
