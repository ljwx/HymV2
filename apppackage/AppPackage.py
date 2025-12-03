class AppPackageInfo:
    def __init__(self, name, package_name, app_version):
        self.name = name
        self.package_name = package_name
        self.app_version = app_version


TestApp = AppPackageInfo("ks", "com.kuaishou.nebula", "1.0.0")
