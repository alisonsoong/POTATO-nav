import Foundation
import Testing
@testable import PassiveNav

struct ARKitEvaluationTests {
    @Test func arkitPoseSampleRoundTripsThroughJSON() throws {
        let sample = ARKitPoseSample(
            id: UUID(),
            timestamp: 1.25,
            unixTimestampS: 1_700_000_000.0,
            rawFrameTimestamp: 100.25,
            callbackUptime: 100.30,
            trackingState: "normal",
            trackingReason: "",
            transformMatrix: Array(repeating: 0.0, count: 16),
            xM: 1.0,
            yM: 2.0,
            zM: -3.0,
            yawRad: 0.5
        )

        let data = try JSONEncoder().encode(sample)
        let decoded = try JSONDecoder().decode(ARKitPoseSample.self, from: data)

        #expect(decoded.timestamp == sample.timestamp)
        #expect(decoded.unixTimestampS == 1_700_000_000.0)
        #expect(decoded.trackingState == "normal")
        #expect(decoded.xM == 1.0)
        #expect(decoded.zM == -3.0)
    }

    @Test func timestampNormalizationUsesRawUptimeWhenItMatchesClock() {
        let timestamp = ARKitPoseRecorder.normalizedTimestamp(
            rawFrameTimestamp: 105.0,
            callbackUptime: 105.1,
            startUptime: 100.0
        )

        #expect(abs(timestamp - 5.0) < 0.000001)
    }

    @Test func timestampNormalizationFallsBackToCallbackUptime() {
        let timestamp = ARKitPoseRecorder.normalizedTimestamp(
            rawFrameTimestamp: 0.25,
            callbackUptime: 105.1,
            startUptime: 100.0
        )

        #expect(abs(timestamp - 5.1) < 0.000001)
    }

    @Test func oldIMUSampleJSONStillDecodes() throws {
        let json = """
        {
          "id": "\(UUID().uuidString)",
          "timestamp": 0.5,
          "gyroX": 1.0,
          "gyroY": 2.0,
          "gyroZ": 3.0,
          "accelX": 4.0,
          "accelY": 5.0,
          "accelZ": 6.0
        }
        """

        let sample = try JSONDecoder().decode(IMUSample.self, from: Data(json.utf8))

        #expect(sample.timestamp == 0.5)
        #expect(sample.userAccelX == nil)
        #expect(sample.accelZ == 6.0)
    }

    @MainActor
    @Test func bundleExportIncludesExpectedFiles() throws {
        let run = SensorEvaluationRun(
            id: UUID(),
            name: "Unit Test",
            mode: .arkitOnly,
            testType: nil,
            startedAt: Date(timeIntervalSince1970: 1),
            endedAt: Date(timeIntervalSince1970: 2),
            sampleInterval: nil,
            notes: "",
            timestampBasis: "process_uptime_seconds",
            recordingStartUptime: 10,
            imuSamples: [],
            arkitFrames: [
                ARKitPoseSample(
                    id: UUID(),
                    timestamp: 0,
                    unixTimestampS: 1,
                    rawFrameTimestamp: 10,
                    callbackUptime: 10,
                    trackingState: "normal",
                    trackingReason: "",
                    transformMatrix: Array(repeating: 0.0, count: 16),
                    xM: 0,
                    yM: 0,
                    zM: 0,
                    yawRad: 0
                )
            ]
        )

        let store = ARKitEvaluationRunStore()
        let names = Set(store.exportURLs(for: run).map(\.lastPathComponent))

        #expect(names.contains("metadata.json"))
        #expect(names.contains("arkit.csv"))
        #expect(!names.contains("imu.csv"))
    }
}
