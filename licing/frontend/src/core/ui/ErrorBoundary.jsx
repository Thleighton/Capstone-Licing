import { Component } from "react";

export default class ErrorBoundary extends Component {
  state = { fallo: false };

  static getDerivedStateFromError() {
    return { fallo: true };
  }

  componentDidCatch(error, info) {
    console.error("Error al mostrar LICING", error, info.componentStack);
  }

  render() {
    if (this.state.fallo) {
      return (
        <main className="content" role="alert">
          <h1>No se pudo mostrar esta pantalla</h1>
          <p>Ocurrió un problema al cargar LICING. Recarga la aplicación para volver a intentarlo.</p>
          <button className="primary" type="button" onClick={() => window.location.reload()}>Recargar LICING</button>
        </main>
      );
    }
    return this.props.children;
  }
}
