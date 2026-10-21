import AppKit

// usage: navdiff <a.png> <b.png> <out-diff.png> [y0 y1]
let args = CommandLine.arguments
let y0 = args.count > 4 ? Int(args[4])! : 130
let y1 = args.count > 5 ? Int(args[5])! : 370

func pixels(_ path: String) -> (CGImage, [UInt8]) {
    let image = NSImage(contentsOfFile: path)!.cgImage(forProposedRect: nil, context: nil, hints: nil)!
    var data = [UInt8](repeating: 0, count: image.width * image.height * 4)
    let context = CGContext(data: &data, width: image.width, height: image.height, bitsPerComponent: 8,
                            bytesPerRow: image.width * 4, space: CGColorSpaceCreateDeviceRGB(),
                            bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!
    context.draw(image, in: CGRect(x: 0, y: 0, width: image.width, height: image.height))
    return (image, data)
}

let (imageA, a) = pixels(args[1])
let (_, b) = pixels(args[2])
let width = imageA.width
var diff = a
var count = 0
var minX = Int.max, maxX = 0, minY = Int.max, maxY = 0
for y in y0..<y1 {
    for x in 0..<width {
        let i = (y * width + x) * 4
        let delta = (0..<3).map { abs(Int(a[i + $0]) - Int(b[i + $0])) }.max()!
        if delta > 2 {
            count += 1
            minX = min(minX, x); maxX = max(maxX, x); minY = min(minY, y); maxY = max(maxY, y)
            diff[i] = 255; diff[i + 1] = 0; diff[i + 2] = 255
        }
    }
}
let context = CGContext(data: &diff, width: width, height: imageA.height, bitsPerComponent: 8, bytesPerRow: width * 4,
                        space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!
let crop = context.makeImage()!.cropping(to: CGRect(x: 0, y: y0, width: width, height: y1 - y0))!
try! NSBitmapImageRep(cgImage: crop).representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: args[3]))
print(count == 0 ? "identical" : "\(count) px differ, bbox x\(minX)-\(maxX) y\(minY)-\(maxY)")
