import SwiftUI

/// The signature card. On levels 5-6 it carries `IntensityPulse`, the one
/// place in the app where motion is allowed to read as "hot" — everywhere
/// else stays calm on purpose (design system, §7).
struct PromptCardView: View {
    let card: Card

    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            HStack {
                Text(card.kind == .dare ? "ПРИГЛАШЕНИЕ" : formatLabel)
                    .font(.caption.bold())
                    .tracking(1.4)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 6)
                    .background(Color.white.opacity(0.18))
                    .clipShape(Capsule())

                Spacer()

                Text("Ур. \(card.intensityLevel)")
                    .font(.caption.bold())
                    .foregroundStyle(.white.opacity(0.7))
            }

            Spacer(minLength: 8)

            Text(card.text)
                .font(.system(size: 30, weight: .semibold, design: .rounded))
                .foregroundStyle(.white)
                .multilineTextAlignment(.center)
                .minimumScaleFactor(0.6)
                .frame(maxWidth: .infinity)

            Spacer(minLength: 8)
        }
        .padding(32)
        .frame(maxWidth: .infinity, minHeight: 340)
        .background(Theme.levelGradient(for: card.intensityLevel))
        .clipShape(RoundedRectangle(cornerRadius: 32, style: .continuous))
        .modifier(IntensityPulse(isActive: Theme.glowsAtHighIntensity(card.intensityLevel)))
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(formatLabel). Уровень \(card.intensityLevel). \(card.text)")
    }

    private var formatLabel: String {
        switch card.answerFormat {
        case .yesNoMaybe: return "ДА / НЕТ / ВОЗМОЖНО"
        case .singleChoice: return "ВЫБЕРИ ВАРИАНТ"
        case .openText: return "ОТКРЫТЫЙ ВОПРОС"
        case .privateAnswer: return "ПРИВАТНЫЙ ОТВЕТ"
        case .simultaneousReveal: return "ОДНОВРЕМЕННОЕ РАСКРЫТИЕ"
        case .matchCheck: return "СОВПАДЕНИЕ"
        case .discussAfter: return "С ОБСУЖДЕНИЕМ"
        case .addOwnOption: return "ДОБАВЬ СВОЙ ВАРИАНТ"
        }
    }
}

/// A slow glow pulse around the card, synced with a light haptic when the
/// card appears (triggered by the view that owns the animation timing).
/// Fully disabled under Reduce Motion, per the design system's rule that
/// "hot" motion is always secondary to accessibility.
struct IntensityPulse: ViewModifier {
    let isActive: Bool
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var pulsing = false

    func body(content: Content) -> some View {
        content
            .shadow(
                color: isActive ? Theme.accentGlow.opacity(pulsing && !reduceMotion ? 0.4 : 0.2) : .clear,
                radius: 24
            )
            .onAppear { startIfNeeded() }
            .onChange(of: isActive) { _, _ in startIfNeeded() }
    }

    private func startIfNeeded() {
        guard isActive, !reduceMotion else {
            pulsing = false
            return
        }
        withAnimation(.easeInOut(duration: 1.0).repeatForever(autoreverses: true)) {
            pulsing = true
        }
    }
}
