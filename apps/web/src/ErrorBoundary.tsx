import { Component, ErrorInfo, ReactNode } from "react";

type Props = {
  children: ReactNode;
};

type State = {
  hasError: boolean;
  message: string;
};

export class ErrorBoundary extends Component<Props, State> {
  state: State = {
    hasError: false,
    message: ""
  };

  static getDerivedStateFromError(error: Error): State {
    return {
      hasError: true,
      message: error.message
    };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("App render failed", error, info.componentStack);
  }

  render() {
    if (this.state.hasError) {
      return (
        <main className="error-shell">
          <section className="error-card">
            <span>Trade Lab Web</span>
            <h1>頁面暫時無法顯示</h1>
            <p>{this.state.message || "未知的前端錯誤"}</p>
            <button type="button" onClick={() => window.location.reload()}>
              重新載入
            </button>
          </section>
        </main>
      );
    }

    return this.props.children;
  }
}
