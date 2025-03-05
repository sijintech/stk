from pyqode.core import backend

if __name__ == '__main__':
    backend.CodeCompletionWorker.providers.append(
        backend.DocumentWordsProvider())
    print("server start")
    backend.serve_forever()
