// Last line of defence for the 3D view: a rendering error in one payload (malformed data that passed
// validation, a vtk.js failure) shows a message in place of the viewer instead of unmounting the app.
// The boundary resets when `resetKey` changes (the next payload or step).
import React from 'react';

interface Props {resetKey?: unknown, children: React.ReactNode}
interface State {error: Error | null, key: unknown}

export default class ErrorBoundary extends React.Component<Props, State> {
  state: State = {error: null, key: this.props.resetKey};
  static getDerivedStateFromError(error: unknown): Partial<State> {
    return {error: error instanceof Error ? error : new Error(String(error))};
  }
  static getDerivedStateFromProps(props: Props, state: State): Partial<State> | null {
    return props.resetKey !== state.key ? {error: null, key: props.resetKey} : null;
  }
  render() {
    if (!this.state.error) return this.props.children;
    return <div className="viewport"><p className="viewer-error" role="alert">三维视图无法显示：{this.state.error.message || String(this.state.error)}</p></div>;
  }
}
