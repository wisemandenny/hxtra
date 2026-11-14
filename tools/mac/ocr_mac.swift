// ocr_mac.swift - the text on a picture of the HX Stomp's screen, with macOS's Vision, for tools/hx_devtest.py.
// Reads a PNG path a line on stdin and writes a JSON line a picture: {"lines": [{"text", "conf", "box": [x, y, w, h]}]}, the box in
// fractions of the picture from its top left. Built into build/ocr_mac on first use.
import AppKit
import Foundation
import Vision

while let path = readLine() {
    var lines: [[String: Any]] = []
    if let img = NSImage(contentsOfFile: path), let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) {
        let req = VNRecognizeTextRequest()
        req.recognitionLevel = .accurate
        req.usesLanguageCorrection = false      // block names and values are not words
        try? VNImageRequestHandler(cgImage: cg).perform([req])
        for o in req.results ?? [] {
            guard let c = o.topCandidates(1).first else { continue }
            let b = o.boundingBox               // Vision's origin is the bottom left
            lines.append(["text": c.string, "conf": c.confidence, "box": [b.minX, 1 - b.maxY, b.width, b.height]])
        }
    }
    let data = try! JSONSerialization.data(withJSONObject: ["lines": lines])
    print(String(data: data, encoding: .utf8)!)
    fflush(stdout)
}
