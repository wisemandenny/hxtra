// noise_mac.swift - play steady white noise into an audio output's channels on macOS.
//   swiftc -O tools/mac/noise_mac.swift -o build/noise_mac
//   ./build/noise_mac "HX Stomp" 8 5,6 -40
// Picks the first output device whose name contains the first argument and plays, for SECONDS,
// white noise (xorshift32, fixed seed, uniform, so the same signal every run) at RMS LEVEL dBFS
// (default -40) on the listed channels (1-based); every other channel is silent. For transfer
// function measurements with tools/hx_freqresp.py: a low level keeps drive blocks in their linear range.
import AVFoundation
import CoreAudio
import Foundation

let args = CommandLine.arguments
guard args.count >= 4, let seconds = Double(args[2]) else {
    FileHandle.standardError.write("usage: noise_mac DEVICE-NAME SECONDS CH[,CH..] [LEVEL_DBFS]\n".data(using: .utf8)!)
    exit(2)
}
let want = args[1]
let chans = args[3].split(separator: ",").compactMap { Int($0) }.map { $0 - 1 }
let levelDb = args.count > 4 ? Double(args[4]) ?? -40 : -40
let amp = Float(pow(10.0, levelDb / 20.0) * 3.0.squareRoot())   // uniform in [-a, a] has RMS a / sqrt(3)
func say(_ s: String) { FileHandle.standardError.write((s + "\n").data(using: .utf8)!) }

func outputDevice(named want: String) -> AudioDeviceID? {
    var addr = AudioObjectPropertyAddress(mSelector: kAudioHardwarePropertyDevices,
                                          mScope: kAudioObjectPropertyScopeGlobal,
                                          mElement: kAudioObjectPropertyElementMain)
    var size: UInt32 = 0
    AudioObjectGetPropertyDataSize(AudioObjectID(kAudioObjectSystemObject), &addr, 0, nil, &size)
    var ids = [AudioDeviceID](repeating: 0, count: Int(size) / MemoryLayout<AudioDeviceID>.size)
    AudioObjectGetPropertyData(AudioObjectID(kAudioObjectSystemObject), &addr, 0, nil, &size, &ids)
    for id in ids {
        var nameAddr = AudioObjectPropertyAddress(mSelector: kAudioObjectPropertyName,
                                                  mScope: kAudioObjectPropertyScopeGlobal,
                                                  mElement: kAudioObjectPropertyElementMain)
        var name: Unmanaged<CFString>?
        var nsize = UInt32(MemoryLayout<Unmanaged<CFString>?>.size)
        AudioObjectGetPropertyData(id, &nameAddr, 0, nil, &nsize, &name)
        var outAddr = AudioObjectPropertyAddress(mSelector: kAudioDevicePropertyStreamConfiguration,
                                                 mScope: kAudioDevicePropertyScopeOutput,
                                                 mElement: kAudioObjectPropertyElementMain)
        var osize: UInt32 = 0
        AudioObjectGetPropertyDataSize(id, &outAddr, 0, nil, &osize)
        if let n = name?.takeRetainedValue() as String?, n.contains(want), osize > UInt32(MemoryLayout<AudioBufferList>.size) - 16 {
            return id
        }
    }
    return nil
}

guard var dev = outputDevice(named: want) else { say("no audio output like '\(want)'"); exit(1) }
let engine = AVAudioEngine()
let out = engine.outputNode
guard let au = out.audioUnit else { exit(1) }
guard AudioUnitSetProperty(au, kAudioOutputUnitProperty_CurrentDevice, kAudioUnitScope_Global, 0,
                           &dev, UInt32(MemoryLayout<AudioDeviceID>.size)) == noErr else {
    say("could not select the device"); exit(1)
}
let fmt = out.outputFormat(forBus: 0)
let nch = Int(fmt.channelCount), rate = fmt.sampleRate
guard chans.allSatisfy({ $0 >= 0 && $0 < nch }) else { say("the device has \(nch) output channels"); exit(1) }
let layout = AVAudioChannelLayout(layoutTag: kAudioChannelLayoutTag_DiscreteInOrder | UInt32(nch))!
let srcFmt = AVAudioFormat(standardFormatWithSampleRate: rate, channelLayout: layout)
var state: UInt32 = 0x9e3779b9
let src = AVAudioSourceNode(format: srcFmt) {
    _, _, frameCount, abl in
    let bufs = UnsafeMutableAudioBufferListPointer(abl)
    for f in 0..<Int(frameCount) {
        state ^= state << 13; state ^= state >> 17; state ^= state << 5
        let v = (Float(state) / Float(UInt32.max) * 2 - 1) * amp
        for (c, b) in bufs.enumerated() {
            b.mData!.assumingMemoryBound(to: Float.self)[f] = chans.contains(c) ? v : 0
        }
    }
    return noErr
}
engine.attach(src)
engine.connect(src, to: out, format: srcFmt)
do { try engine.start() } catch { say("engine: \(error)"); exit(1) }
say("playing white noise (\(levelDb) dBFS RMS) on channel(s) \(chans.map { $0 + 1 }) of \(nch) at \(Int(rate)) Hz for \(seconds) s")
Thread.sleep(forTimeInterval: seconds)
engine.stop()
