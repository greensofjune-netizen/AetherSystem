// Compile and bundle as galileo-voice beside desktop_voice.py (macOS 12+).
import AVFoundation
import Darwin
import Foundation
import Speech

final class Dictation {
    private let engine = AVAudioEngine()
    private var request: SFSpeechAudioBufferRecognitionRequest?
    private var task: SFSpeechRecognitionTask?
    private var signalSource: DispatchSourceSignal?
    private var stopSource: DispatchSourceRead?
    private var transcript = ""
    private var tapped = false
    private var finishing = false
    private var completed = false

    func start() {
        // Install before permission prompts; a stop request must not kill the helper.
        signal(SIGUSR1, SIG_IGN)
        let source = DispatchSource.makeSignalSource(signal: SIGUSR1, queue: .main)
        source.setEventHandler { self.endCapture() }
        signalSource = source
        source.resume()
        if CommandLine.arguments.count == 3,
           CommandLine.arguments[1] == "--stop-fd",
           let descriptor = Int32(CommandLine.arguments[2]), descriptor >= 3 {
            let stop = DispatchSource.makeReadSource(fileDescriptor: descriptor, queue: .main)
            stop.setEventHandler {
                self.endCapture()
                self.stopSource?.cancel()
            }
            stop.setCancelHandler { close(descriptor) }
            stopSource = stop
            stop.resume()
        } else if CommandLine.arguments.count != 1 {
            fail("Invalid native dictation helper arguments.")
            return
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 50) {
            self.fail("Dictation timed out. Check Speech and microphone permissions.")
        }
        switch SFSpeechRecognizer.authorizationStatus() {
        case .authorized:
            microphoneAuthorization()
        case .notDetermined:
            SFSpeechRecognizer.requestAuthorization { status in
                DispatchQueue.main.async {
                    guard !self.completed, !self.finishing else { return }
                    if status == .authorized {
                        self.microphoneAuthorization()
                    } else {
                        self.speechDenied(status)
                    }
                }
            }
        case .denied, .restricted:
            speechDenied(SFSpeechRecognizer.authorizationStatus())
        @unknown default:
            fail("Speech recognition authorization is unavailable.")
        }
    }

    private func speechDenied(_ status: SFSpeechRecognizerAuthorizationStatus) {
        fail(status == .restricted
             ? "Speech recognition is restricted on this Mac."
             : "Speech permission denied. Enable Galileo in System Settings > Privacy & Security > Speech Recognition.")
    }

    private func microphoneAuthorization() {
        guard !completed, !finishing else { return }
        switch AVCaptureDevice.authorizationStatus(for: .audio) {
        case .authorized:
            recognize()
        case .notDetermined:
            AVCaptureDevice.requestAccess(for: .audio) { allowed in
                DispatchQueue.main.async {
                    guard !self.completed, !self.finishing else { return }
                    if allowed {
                        self.recognize()
                    } else {
                        self.microphoneDenied()
                    }
                }
            }
        case .denied, .restricted:
            microphoneDenied()
        @unknown default:
            fail("Microphone authorization is unavailable.")
        }
    }

    private func microphoneDenied() {
        fail("Microphone permission denied or restricted. Enable Galileo in System Settings > Privacy & Security > Microphone.")
    }

    private func recognize() {
        guard !completed, !finishing else { return }
        guard let recognizer = SFSpeechRecognizer(locale: Locale.current),
              recognizer.supportsOnDeviceRecognition else {
            fail("On-device speech recognition is unavailable for this Mac or language. No network fallback is used.")
            return
        }
        guard recognizer.isAvailable else {
            fail("On-device speech recognition is currently unavailable.")
            return
        }
        let audioRequest = SFSpeechAudioBufferRecognitionRequest()
        audioRequest.requiresOnDeviceRecognition = true
        audioRequest.shouldReportPartialResults = true
        request = audioRequest
        let input = engine.inputNode
        let format = input.outputFormat(forBus: 0)
        guard format.sampleRate > 0, format.channelCount > 0 else {
            fail("No usable microphone is available.")
            return
        }
        input.installTap(onBus: 0, bufferSize: 1024, format: format) { buffer, _ in
            audioRequest.append(buffer)
        }
        tapped = true
        engine.prepare()
        do {
            try engine.start()
        } catch {
            fail("Unable to start microphone capture: \(error.localizedDescription)")
            return
        }
        task = recognizer.recognitionTask(with: audioRequest) { result, error in
            DispatchQueue.main.async {
                guard !self.completed else { return }
                if let result = result {
                    self.transcript = result.bestTranscription.formattedString
                    if result.isFinal {
                        self.finishTranscript()
                        return
                    }
                }
                if let error = error {
                    if self.finishing && !self.transcript.isEmpty {
                        self.finishTranscript()
                    } else {
                        self.fail("On-device recognition failed: \(error.localizedDescription)")
                    }
                }
            }
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 15) { self.endCapture() }
    }

    private func stopAudio() {
        engine.stop()
        if tapped {
            engine.inputNode.removeTap(onBus: 0)
            tapped = false
        }
        request?.endAudio()
    }

    private func endCapture() {
        guard !completed, !finishing else { return }
        finishing = true
        stopAudio()
        // Give the recognizer time to finalize; keep its last partial if it doesn't.
        DispatchQueue.main.asyncAfter(deadline: .now() + 2) { self.finishTranscript() }
    }

    private func finishTranscript() {
        let text = transcript.trimmingCharacters(in: .whitespacesAndNewlines)
        if text.isEmpty {
            fail("No speech was recognized.")
        } else {
            finish(["ok": true, "text": text])
        }
    }

    private func fail(_ message: String) {
        finish(["ok": false, "error": message])
    }

    private func finish(_ result: [String: Any]) {
        guard !completed else { return }
        completed = true
        stopAudio()
        task?.cancel()
        signalSource?.cancel()
        stopSource?.cancel()
        do {
            let data = try JSONSerialization.data(withJSONObject: result)
            FileHandle.standardOutput.write(data)
            FileHandle.standardOutput.write(Data([10]))
            exit(EXIT_SUCCESS)
        } catch {
            FileHandle.standardError.write(Data("Unable to encode dictation result.\n".utf8))
            exit(EXIT_FAILURE)
        }
    }
}

let dictation = Dictation()
DispatchQueue.main.async { dictation.start() }
dispatchMain()
