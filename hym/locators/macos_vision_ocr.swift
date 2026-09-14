import Foundation
import ImageIO
import Vision

struct TextItem: Codable {
    let text: String
    let confidence: Float
    let left: Double
    let top: Double
    let right: Double
    let bottom: Double
}

guard CommandLine.arguments.count >= 3 else {
    fputs("用法: macos_vision_ocr 图片路径 语言 [识别级别]\n", stderr)
    exit(2)
}

let imageURL = URL(fileURLWithPath: CommandLine.arguments[1])
let language = CommandLine.arguments[2]
let level = CommandLine.arguments.count >= 4 ? CommandLine.arguments[3] : "accurate"

guard
    let source = CGImageSourceCreateWithURL(imageURL as CFURL, nil),
    let image = CGImageSourceCreateImageAtIndex(source, 0, nil)
else {
    fputs("无法读取图片\n", stderr)
    exit(3)
}

let request = VNRecognizeTextRequest()
request.recognitionLevel = level == "fast" ? .fast : .accurate
request.recognitionLanguages = [language]
request.usesLanguageCorrection = false

do {
    try VNImageRequestHandler(cgImage: image).perform([request])
    let items = (request.results ?? []).compactMap { observation -> TextItem? in
        guard let candidate = observation.topCandidates(1).first else { return nil }
        let box = observation.boundingBox
        let top = 1.0 - box.origin.y - box.height
        return TextItem(
            text: candidate.string,
            confidence: candidate.confidence,
            left: box.origin.x,
            top: top,
            right: box.origin.x + box.width,
            bottom: top + box.height
        )
    }
    let data = try JSONEncoder().encode(items)
    FileHandle.standardOutput.write(data)
} catch {
    fputs("OCR识别失败: \(error)\n", stderr)
    exit(4)
}
