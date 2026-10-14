import { render, screen } from "@testing-library/react";
import { App } from "../src/app/App";

test("exibe o nome do produto como título principal", () => {
  render(<App />);
  expect(screen.getByRole("heading", { level: 1, name: "BoardHub" })).toBeInTheDocument();
});
