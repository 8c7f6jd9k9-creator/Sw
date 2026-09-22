import SwiftUI

struct CardView: View {
    @EnvironmentObject var store: GameStore
    let card: GameCard

    var body: some View {
        VStack(spacing: 20) {
            HStack {
                Text(card.kind == .dare ? "ДЕЙСТВИЕ" : card.category.uppercased())
                    .font(.caption.bold())
                    .tracking(1.4)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 6)
                    .background(Color.white.opacity(0.25))
                    .clipShape(Capsule())

                Spacer()

                Button {
                    store.toggleFavorite(card)
                } label: {
                    Image(systemName: store.isFavorite(card) ? "heart.fill" : "heart")
                        .font(.title3)
                }
                .buttonStyle(.plain)
                .accessibilityLabel(store.isFavorite(card) ? "Убрать из копилки" : "Добавить в копилку")
            }

            Spacer(minLength: 8)

            Text(card.text)
                .font(.system(size: 28, weight: .semibold, design: .rounded))
                .multilineTextAlignment(.center)
                .minimumScaleFactor(0.6)
                .padding(.horizontal, 6)

            Spacer(minLength: 8)
        }
        .foregroundStyle(.white)
        .padding(28)
        .frame(maxWidth: .infinity, minHeight: 320)
        .background(LevelTheme.gradient(for: card.levelID))
        .clipShape(RoundedRectangle(cornerRadius: 28, style: .continuous))
        .shadow(color: .black.opacity(0.18), radius: 16, y: 8)
        .accessibilityElement(children: .combine)
    }
}
