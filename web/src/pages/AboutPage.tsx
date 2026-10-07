import { COPY } from "../lib/copy";

export function AboutPage() {
  return (
    <section>
      <h1>How the forecasts work</h1>
      <p>
        Each evening after the Nairobi Securities Exchange closes, the system checks the day's
        end-of-day prices. For actively traded stocks it then estimates the next session's
        official closing price, with an 80% expected range.
      </p>
      <h2>What the numbers mean</h2>
      <p>
        The official closing price is the volume-weighted average price of the whole session.
        The 80% expected range is where the actual close fell about 8 times in 10 in past
        testing; it is an estimate, not a promise. Every forecast is compared with a no-change
        guess, and the track record shows both, labelled live or simulated.
      </p>
      <h2>Limitations</h2>
      <p>
        Next-day price changes are hard to predict, and a forecast close to today's price is
        the usual result. Thinly traded stocks get no forecast. Forecasts do not account for
        news, results announcements or dealing costs.
      </p>
      <h2>Data sources</h2>
      <p>{COPY.attribution}</p>
      <p>{COPY.disclaimer}</p>
    </section>
  );
}
