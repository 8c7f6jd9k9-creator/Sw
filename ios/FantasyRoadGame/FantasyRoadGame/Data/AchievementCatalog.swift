import Foundation

enum AchievementCatalog {

    static let all: [Achievement] = [
        Achievement(
            id: "first_card",
            title: "Первый шаг",
            subtitle: "Сыграна первая карточка",
            icon: "sparkles"
        ) { store in
            store.stats.totalCardsPlayed >= 1
        },

        Achievement(
            id: "ten_cards",
            title: "Разговорились",
            subtitle: "Сыграно 10 карточек",
            icon: "bubble.left.and.bubble.right.fill"
        ) { store in
            store.stats.totalCardsPlayed >= 10
        },

        Achievement(
            id: "fifty_cards",
            title: "В своей тарелке",
            subtitle: "Сыграно 50 карточек",
            icon: "flame.fill"
        ) { store in
            store.stats.totalCardsPlayed >= 50
        },

        Achievement(
            id: "hundred_cards",
            title: "Опытная пара",
            subtitle: "Сыграно 100 карточек",
            icon: "star.fill"
        ) { store in
            store.stats.totalCardsPlayed >= 100
        },

        Achievement(
            id: "explorers",
            title: "Исследователи",
            subtitle: "Сыграна хотя бы одна карточка на каждом из 6 уровней",
            icon: "map.fill"
        ) { store in
            (1...6).allSatisfy { (store.stats.perLevelPlayed[$0] ?? 0) > 0 }
        },

        Achievement(
            id: "level5_deep",
            title: "Без фильтра",
            subtitle: "На уровне «Без фильтра» сыграно 20 карточек",
            icon: "flame.circle.fill"
        ) { store in
            (store.stats.perLevelPlayed[5] ?? 0) >= 20
        },

        Achievement(
            id: "level6_deep",
            title: "Честный разговор",
            subtitle: "На уровне «Границы возможного» сыграно 10 карточек",
            icon: "key.fill"
        ) { store in
            (store.stats.perLevelPlayed[6] ?? 0) >= 10
        },

        Achievement(
            id: "collector",
            title: "Коллекционер",
            subtitle: "В копилке 10 карточек",
            icon: "heart.fill"
        ) { store in
            store.favoriteIDs.count >= 10
        },

        Achievement(
            id: "scenario_fan",
            title: "Режиссёр вечера",
            subtitle: "Сохранено 5 сценариев",
            icon: "theatermasks.fill"
        ) { store in
            store.savedScenarios.count >= 5
        },

        Achievement(
            id: "custom_author",
            title: "Автор",
            subtitle: "Добавлена хотя бы одна своя карточка",
            icon: "pencil"
        ) { store in
            !store.customCards.isEmpty
        }
    ]
}
