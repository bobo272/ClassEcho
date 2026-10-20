import AppKit
let directory = URL(fileURLWithPath: CommandLine.arguments[1], isDirectory: true)
try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
for size in [16, 32, 128, 256, 512] {
    for scale in [1, 2] {
        let pixels = size * scale
        let image = NSImage(size: NSSize(width: pixels, height: pixels))
        image.lockFocus()
        let side = CGFloat(pixels)
        NSColor(calibratedWhite: 0.14, alpha: 1).setFill()
        NSBezierPath(roundedRect: NSRect(x: side * 0.06, y: side * 0.06, width: side * 0.88, height: side * 0.88), xRadius: side * 0.18, yRadius: side * 0.18).fill()
        NSColor.white.setStroke()
        let outline = NSBezierPath(rect: NSRect(x: side * 0.28, y: side * 0.2, width: side * 0.44, height: side * 0.6))
        outline.lineWidth = side * 0.035; outline.stroke()
        let lines = NSBezierPath(); lines.lineWidth = side * 0.035
        for y in [0.62, 0.5, 0.38] {
            lines.move(to: NSPoint(x: side * 0.37, y: side * y)); lines.line(to: NSPoint(x: side * 0.63, y: side * y))
        }
        lines.stroke(); image.unlockFocus()
        let bitmap = NSBitmapImageRep(data: image.tiffRepresentation!)!
        try bitmap.representation(using: .png, properties: [:])!.write(to: directory.appendingPathComponent("icon_\(size)x\(size)\(scale == 2 ? "@2x" : "").png"))
    }
}
