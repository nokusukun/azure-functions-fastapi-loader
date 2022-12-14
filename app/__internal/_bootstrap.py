import glob
import threading
import traceback
from importlib import util
import os.path
import sys
import requests
import datetime

from fastapi.responses import RedirectResponse


class Logger:
    def __init__(self, service: str):
        self.service = service
        self.id = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")

        self.url = (
            f"https://servicelogssea.blob.core.windows.net/servicelogs/{self.service}-{self.id}.txt?sp=cw&st=2022"
            f"-06-27T13:36:58Z"
            "&se=2023-06-27T21:36:58Z&spr=https&sv=2021-06-08&sr=c&sig=sBZv%2FcVZUDUWb4JSILKIm"
            "%2FQ7Ttc4gmyFnwciEVhK3Eg%3D"
        )

        payload = {}
        headers = {"x-ms-blob-type": "AppendBlob"}
        requests.request("PUT", self.url, headers=headers, data=payload)

    def _log(self, level: str, message: str, *args):
        if message.count("{}") <= len(args):
            message += " {}" * (len(args) - message.count("{}"))

        args = [f"{x}" for x in args]
        message = f"[{self.service}][{datetime.datetime.now().isoformat()}][{level}] {message.format(*args)}"
        print(message)

        payload = message + "\n"
        headers = {"x-ms-blob-type": "AppendBlob", "Content-Type": "text/plain"}

        def send_log():
            print("Sending request")
            requests.request(
                "PUT", self.url + "&comp=appendblock", headers=headers, data=payload
            )

        threading.Thread(None, send_log, daemon=True).start()

    def Info(self, message: str, *args):
        self._log("INFO", message, *args)

    def Debug(self, message: str, *args):
        self._log("DEBU", message, *args)

    def Error(self, message: str, *args):
        self._log("ERRO", message, *args)


class Function:
    __log = None

    @staticmethod
    def _dummy_function():
        ...

    @property
    def log(self):
        if not self.__log:
            self.__log = Logger(f"{self.__class__.__name__}")
        return self.__log


class ConfigBase:
    def __init__(self, autoload=True):
        if autoload:
            self.Load()

    def Load(self):
        for x in self.__dir__():
            if x.startswith("__"):
                continue
            if callable(getattr(self, x)):
                continue
            if method := getattr(self, f"resolve_{x}", None):
                self.__dict__[x] = method()
            else:
                self.__dict__[x] = os.getenv(x, getattr(self, x))
        try:
            with open(".env") as f:
                lines = f.readlines()

            for i, line in enumerate(lines):
                x = line.split("=")
                if len(x) == 2:
                    self.__dict__[x[0]] = x[1]
                else:
                    print(f"Warning: .env produced an invalid entry in line {i + 1}")
        except FileNotFoundError:
            ...

        return self


def bootstrap(app):
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    bootstraps = []

    @app.get("/stage")
    def stage():
        return os.getenv("stage", "development")

    @app.get("/")
    def status():
        return RedirectResponse("/docs")

    """
    Look for files inside of the './app/functions' directory and 
    attempt to load any classes that has 'Function' subclassed.
    """
    for fn_str in glob.glob(os.path.join("src", "api", "**.py")):
        module_name = os.path.split(fn_str)[-1].replace(".py", "")
        spec = util.spec_from_file_location(module_name, fn_str)
        module = util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        fn = None
        for attr_str in dir(module):
            attr = getattr(module, attr_str)
            if "_bootstrap.Function" in f"{attr}":
                continue
            if getattr(attr, "_dummy_function", None):
                fn = attr

        if fn:
            if (getattr(module, "__init__", None)) is not None:
                print("Initializing:", fn)

                def error(*msg: any, warn=False):
                    if warn:
                        warnings.append(
                            {"info": " ".join(msg), "function": module_name}
                        )
                        return
                    errors.append({"info": " ".join(msg), "function": module_name})

                try:
                    fn = fn(error)
                except Exception as e:
                    exc_type, exc_value, exc_traceback = sys.exc_info()
                    errors.append(
                        {
                            "info": f"Init raised an exception: {''.join(traceback.format_exception(exc_type, exc_value, exc_traceback))}",
                            "function": module_name,
                        }
                    )

            if (getattr(fn, "Bootstrap", None)) is not None:
                bootstraps.append({"class": fn, "name": module_name})

    """
    Check if there are errors thrown that aren't warnings. These errors are generated by the Init method.
    Warnings would still let the modules load but errors would not.
    """
    if not errors:
        for bs in bootstraps:
            print(f"Bootstrapping: {bs['name']}")
            bs["class"].Bootstrap(app)
    else:
        print("ERROR: FUNCTIONS FAILED TO START\n\tCheck /docs for more info")
        app.description += """\n\n***Error: API Failed to start***\n"""
        for err in errors:
            trace = err["info"].replace("\n", "\n\t\t")
            app.description += f"\n\t[{err['function']}]: {trace}"

    if warnings:
        app.description += """\n\n***API Returned warnings***\n"""
        for err in warnings:
            trace = err["info"].replace("\n", "\n\t\t")
            app.description += f"\n\t[{err['function']}]: {trace}"
