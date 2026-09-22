import SwiftUI

/// Color tokens from the PRD's design system (§7). Saturation and warmth
/// rise with intensity level; only `accentGlow` is a bright accent, reserved
/// for levels 5-6.
enum Theme {
    static let backgroundPrimary = Color(hex: "14121A")
    static let backgroundCard = Color(hex: "1F1B29")
    static let accentPrimary = Color(hex: "A8577B")
    static let accentSecondary = Color(hex: "C9915B")
    static let accentGlow = Color(hex: "FF6B9D")
    static let signalSafe = Color(hex: "6FA98C")
    static let signalCaution = Color(hex: "D9A441")
    static let signalStop = Color(hex: "C15B5B")
    static let textPrimary = Color(hex: "F2EDE9")

    static func levelGradient(for level: Int) -> LinearGradient {
        let colors: [Color]
        switch level {
        case 1: colors = [accentPrimary.opacity(0.55), accentPrimary.opacity(0.75)]
        case 2: colors = [accentPrimary.opacity(0.75), accentPrimary]
        case 3: colors = [accentPrimary, accentSecondary]
        case 4: colors = [accentSecondary, Color(hex: "B24A6B")]
        case 5: colors = [Color(hex: "B24A6B"), Color(hex: "7A2E4D")]
        case 6: colors = [Color(hex: "7A2E4D"), Color(hex: "3A1526")]
        default: colors = [accentPrimary, accentSecondary]
        }
        return LinearGradient(colors: colors, startPoint: .topLeading, endPoint: .bottomTrailing)
    }

    /// Levels 5-6 get the signature warm glow described in the design system.
    static func glowsAtHighIntensity(_ level: Int) -> Bool {
        level >= 5
    }
}

extension Color {
    init(hex: String) {
        let scanner = Scanner(string: hex)
        var rgbValue: UInt64 = 0
        scanner.scanHexInt64(&rgbValue)
        let red = Double((rgbValue & 0xFF0000) >> 16) / 255
        let green = Double((rgbValue & 0x00FF00) >> 8) / 255
        let blue = Double(rgbValue & 0x0000FF) / 255
        self.init(red: red, green: green, blue: blue)
    }
}
