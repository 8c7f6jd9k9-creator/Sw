import SwiftUI

struct ProgressHeaderView: View {
    @EnvironmentObject var store: GameStore

    var body: some View {
        HStack(alignment: .top) {
            VStack(alignment: .leading, spacing: 2) {
                Text(store.currentLevel.emoji + " " + store.currentLevel.title)
                    .font(.title3.bold())
                Text(store.currentLevel.subtitle)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Spacer()

            if store.totalCardsInLevel > 0 {
                VStack(alignment: .trailing, spacing: 2) {
                    Text("Карта \(store.cardsSeenInRound) из \(store.totalCardsInLevel)")
                        .font(.subheadline.bold())
                    if store.roundNumber > 1 {
                        Text("Круг \(store.roundNumber)")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
            }
        }
    }
}
