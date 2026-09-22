import SwiftUI

struct GameScreenView: View {
    @EnvironmentObject var store: SessionStore
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    @State private var cardOpacity: Double = 1
    @State private var cardOffset: CGFloat = 0

    var body: some View {
        ScrollView {
            VStack(spacing: 20) {
                header

                if let card = store.currentCard {
                    PromptCardView(card: card)
                        .opacity(cardOpacity)
                        .offset(y: cardOffset)
                        .id(card.id)
                        .onAppear { animateIn() }
                } else {
                    emptyDeckCard
                }

                actionButtons

                Text("Любую карточку можно пропустить без объяснений.")
                    .font(.footnote)
                    .foregroundStyle(Theme.textPrimary.opacity(0.5))
            }
            .padding(28)
            .frame(maxWidth: 640)
            .frame(maxWidth: .infinity)
            .padding(.top, 40)
        }
        .sheet(isPresented: Binding(
            get: { store.showCheckIn },
            set: { if !$0 { store.dismissCheckIn() } }
        )) {
            CheckInView()
                .presentationDetents([.medium])
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text("Уровень \(store.session?.intensityLevel ?? 1)")
                    .font(.headline)
                    .foregroundStyle(Theme.textPrimary)
                Spacer()
                if store.totalCardsInRound > 0 {
                    Text("Карта \(store.cardsSeenInRound) из \(store.totalCardsInRound)")
                        .font(.subheadline)
                        .foregroundStyle(Theme.textPrimary.opacity(0.6))
                }
            }
            if store.roundNumber > 1 {
                Text("Круг \(store.roundNumber)")
                    .font(.caption)
                    .foregroundStyle(Theme.textPrimary.opacity(0.5))
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var emptyDeckCard: some View {
        VStack(spacing: 14) {
            Image(systemName: "checkmark.seal")
                .font(.system(size: 44))
                .foregroundStyle(Theme.accentSecondary)
            Text("На этом уровне пока нет доступных карточек")
                .font(.headline)
                .foregroundStyle(Theme.textPrimary)
            Text("Возможно, кто-то отметил все темы уровня как «точно нет», либо не хватает согласия. Загляните в паузу, чтобы проверить границы.")
                .font(.subheadline)
                .foregroundStyle(Theme.textPrimary.opacity(0.6))
                .multilineTextAlignment(.center)
        }
        .padding(40)
        .frame(maxWidth: .infinity)
        .background(Theme.backgroundCard)
        .clipShape(RoundedRectangle(cornerRadius: 28, style: .continuous))
    }

    private var actionButtons: some View {
        HStack(spacing: 16) {
            Button {
                store.requestAdvance()
            } label: {
                Label("Пропустить", systemImage: "forward.fill")
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.bordered)
            .controlSize(.large)
            .disabled(store.currentCard == nil)

            Button {
                store.requestAdvance()
            } label: {
                Label("Дальше", systemImage: "arrow.right.circle.fill")
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent)
            .tint(Theme.accentPrimary)
            .controlSize(.large)
            .disabled(store.currentCard == nil)
        }
    }

    private func animateIn() {
        guard !reduceMotion else {
            cardOpacity = 1
            cardOffset = 0
            return
        }
        cardOpacity = 0
        cardOffset = 12
        withAnimation(.easeOut(duration: 0.25)) {
            cardOpacity = 1
            cardOffset = 0
        }
    }
}
