import SwiftUI

struct FavoritesView: View {
    @EnvironmentObject var store: GameStore
    @State private var cardToShare: GameCard?

    var body: some View {
        NavigationStack {
            Group {
                if store.favoriteCards.isEmpty {
                    ContentUnavailableView(
                        "Копилка пока пуста",
                        systemImage: "heart",
                        description: Text("Добавляйте понравившиеся карточки во время игры.")
                    )
                } else {
                    List {
                        ForEach(groupedFavorites, id: \.category) { group in
                            Section(group.category) {
                                ForEach(group.cards) { card in
                                    Text(card.text)
                                        .padding(.vertical, 4)
                                        .swipeActions(edge: .trailing) {
                                            Button(role: .destructive) {
                                                store.removeFavorite(card)
                                            } label: {
                                                Label("Удалить", systemImage: "trash")
                                            }
                                        }
                                        .swipeActions(edge: .leading) {
                                            Button {
                                                cardToShare = card
                                            } label: {
                                                Label("Поделиться", systemImage: "square.and.arrow.up")
                                            }
                                            .tint(.blue)
                                        }
                                }
                            }
                        }
                    }
                }
            }
            .navigationTitle("Копилка")
            .sheet(item: $cardToShare) { card in
                ShareSheet(items: [card.text])
            }
        }
    }

    private var groupedFavorites: [(category: String, cards: [GameCard])] {
        let grouped = Dictionary(grouping: store.favoriteCards, by: { $0.category })
        return grouped.keys.sorted().map { key in
            (category: key, cards: grouped[key] ?? [])
        }
    }
}
