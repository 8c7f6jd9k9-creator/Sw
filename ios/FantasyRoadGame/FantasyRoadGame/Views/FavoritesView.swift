import SwiftUI

struct FavoritesView: View {
    @EnvironmentObject var store: GameStore
    @State private var cardToShare: GameCard?
    @State private var scenarioToShare: GeneratedScenario?

    var body: some View {
        NavigationStack {
            Group {
                if store.favoriteCards.isEmpty && store.savedScenarios.isEmpty {
                    ContentUnavailableView(
                        "Копилка пока пуста",
                        systemImage: "heart",
                        description: Text("Добавляйте понравившиеся карточки и сценарии во время игры.")
                    )
                } else {
                    List {
                        if !store.savedScenarios.isEmpty {
                            Section("Сохранённые сценарии") {
                                ForEach(store.savedScenarios) { scenario in
                                    Text(scenario.sentence)
                                        .padding(.vertical, 4)
                                        .swipeActions(edge: .trailing) {
                                            Button(role: .destructive) {
                                                store.removeScenario(scenario)
                                            } label: {
                                                Label("Удалить", systemImage: "trash")
                                            }
                                        }
                                        .swipeActions(edge: .leading) {
                                            Button {
                                                scenarioToShare = scenario
                                            } label: {
                                                Label("Поделиться", systemImage: "square.and.arrow.up")
                                            }
                                            .tint(.blue)
                                        }
                                }
                            }
                        }

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
            .sheet(item: $scenarioToShare) { scenario in
                ShareSheet(items: [scenario.sentence])
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
