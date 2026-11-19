import CryptoKit
import Darwin
import Foundation

public struct ReleaseIdentity: Codable, Equatable, Sendable {
    public static let schemaName = "dev-main-sync-release/v1"
    public static let version = "0.9.0"
    public static let buildNumber = "14"
    public static let minimumSystemVersion = "26.0"
    private static let supportedVersions = [
        "0.1.0", "0.2.0", "0.3.0", "0.4.0", "0.5.0",
        "0.6.0", "0.7.0", "0.8.0",
        version,
    ]

    public let schema: String
    public let version: String
    public let buildNumber: String
    public let sourceRevision: String
    public let sourceInputSHA256: String
    public let metadataContractSHA256: String
    public let architecture: String
    public let minimumSystemVersion: String
    public let buildMode: String

    public init(
        sourceRevision: String,
        sourceInputSHA256: String,
        metadataContractSHA256: String,
        architecture: String,
        buildMode: String
    ) throws {
        schema = Self.schemaName
        version = Self.version
        buildNumber = Self.buildNumber
        self.sourceRevision = sourceRevision
        self.sourceInputSHA256 = sourceInputSHA256
        self.metadataContractSHA256 = metadataContractSHA256
        self.architecture = architecture
        minimumSystemVersion = Self.minimumSystemVersion
        self.buildMode = buildMode
        try validate()
    }

    public init(infoDictionary: [String: Any]) throws {
        func string(_ key: String) throws -> String {
            guard let value = infoDictionary[key] as? String else {
                throw ReleaseIdentityError.missingMetadata(key)
            }
            return value
        }
        schema = try string("DevMainSyncReleaseSchema")
        version = try string("CFBundleShortVersionString")
        buildNumber = try string("CFBundleVersion")
        sourceRevision = try string("DevMainSyncSourceRevision")
        sourceInputSHA256 = try string("DevMainSyncSourceInputSHA256")
        metadataContractSHA256 = try string("DevMainSyncMetadataContractSHA256")
        architecture = try string("DevMainSyncArchitecture")
        minimumSystemVersion = try string("LSMinimumSystemVersion")
        buildMode = try string("DevMainSyncBuildMode")
        try validate()
    }

    public static func load(bundlePath: String) throws -> ReleaseIdentity {
        let plist = URL(fileURLWithPath: bundlePath)
            .appendingPathComponent("Contents/Info.plist").path
        guard let dictionary = NSDictionary(contentsOfFile: plist) as? [String: Any] else {
            throw ReleaseIdentityError.invalidInfoPlist
        }
        return try ReleaseIdentity(infoDictionary: dictionary)
    }

    public func validate(requireProduction: Bool = false) throws {
        let currentBuild = Int(Self.buildNumber) ?? 0
        let observedBuild = Int(buildNumber) ?? 0
        guard schema == Self.schemaName,
              Self.supportedVersions.contains(version),
              observedBuild >= 1,
              observedBuild <= currentBuild,
              minimumSystemVersion == Self.minimumSystemVersion,
              Self.isHex(sourceRevision, count: 40),
              Self.isHex(sourceInputSHA256, count: 64),
              Self.isHex(metadataContractSHA256, count: 64),
              ["arm64", "x86_64"].contains(architecture),
              ["production", "testing"].contains(buildMode),
              !requireProduction || (
                buildMode == "production"
                    && sourceRevision != String(repeating: "0", count: 40)
                    && sourceInputSHA256 != String(repeating: "0", count: 64)
                    && metadataContractSHA256 != String(repeating: "0", count: 64)
              ) else {
            throw ReleaseIdentityError.invalidMetadata
        }
    }

    public func sameInstallContract(as other: ReleaseIdentity) -> Bool {
        version == other.version
            && buildNumber == other.buildNumber
            && sourceInputSHA256 == other.sourceInputSHA256
            && metadataContractSHA256 == other.metadataContractSHA256
            && architecture == other.architecture
            && minimumSystemVersion == other.minimumSystemVersion
            && buildMode == other.buildMode
    }

    private static func isHex(_ value: String, count: Int) -> Bool {
        value.count == count && value.utf8.allSatisfy {
            (48...57).contains($0) || (97...102).contains($0)
        }
    }
}

public struct BundleArtifactIdentity: Equatable, Sendable {
    public let release: ReleaseIdentity
    public let canonicalSHA256: String
    public let inventory: [String]

    public static func inspect(
        bundlePath: String,
        requireProduction: Bool = false
    ) throws -> BundleArtifactIdentity {
        var rootInfo = stat()
        guard lstat(bundlePath, &rootInfo) == 0,
              (rootInfo.st_mode & S_IFMT) == S_IFDIR,
              rootInfo.st_uid == geteuid(),
              rootInfo.st_flags == 0,
              hasOnlyPermittedXattrs(bundlePath) else {
            throw ReleaseIdentityError.unsafeBundle(bundlePath)
        }
        let release = try ReleaseIdentity.load(bundlePath: bundlePath)
        try release.validate(requireProduction: requireProduction)

        guard let enumerator = FileManager.default.enumerator(
            at: URL(fileURLWithPath: bundlePath),
            includingPropertiesForKeys: nil,
            options: []
        ) else {
            throw ReleaseIdentityError.unsafeBundle(bundlePath)
        }
        var records: [String] = [
            "d\u{0}.\u{0}\(rootInfo.st_mode & 0o7777)\u{0}0\u{0}-",
        ]
        let root = bundlePath + "/"
        for case let url as URL in enumerator {
            let path = url.path
            guard path.hasPrefix(root) else {
                throw ReleaseIdentityError.unsafeBundle(path)
            }
            let relative = String(path.dropFirst(root.count))
            guard !relative.isEmpty, !relative.contains("\n"), !relative.contains("\0") else {
                throw ReleaseIdentityError.unsafeBundle(relative)
            }
            var info = stat()
            guard lstat(path, &info) == 0,
                  info.st_uid == geteuid(),
                  info.st_flags == 0,
                  hasOnlyPermittedXattrs(path) else {
                throw ReleaseIdentityError.unsafeBundle(relative)
            }
            let type = info.st_mode & S_IFMT
            let mode = info.st_mode & 0o7777
            if type == S_IFDIR {
                records.append("d\u{0}\(relative)\u{0}\(mode)\u{0}0\u{0}-")
            } else if type == S_IFREG, info.st_nlink == 1 {
                let data = try Data(contentsOf: url, options: [.mappedIfSafe])
                let digest = SHA256.hash(data: data).hex
                records.append("f\u{0}\(relative)\u{0}\(mode)\u{0}\(info.st_size)\u{0}\(digest)")
            } else {
                throw ReleaseIdentityError.unsafeBundle(relative)
            }
        }
        records.sort()
        let bytes = Data((records.joined(separator: "\u{0}") + "\u{0}").utf8)
        return BundleArtifactIdentity(
            release: release,
            canonicalSHA256: SHA256.hash(data: bytes).hex,
            inventory: records
        )
    }

    static func hasOnlyPermittedXattrs(_ path: String) -> Bool {
        let size = listxattr(path, nil, 0, XATTR_NOFOLLOW)
        guard size >= 0 else { return false }
        if size == 0 { return true }
        var bytes = [CChar](repeating: 0, count: size)
        let read = bytes.withUnsafeMutableBufferPointer {
            listxattr(path, $0.baseAddress, size, XATTR_NOFOLLOW)
        }
        guard read == size else { return false }
        let names = bytes.split(separator: 0).map {
            String(decoding: $0.map { UInt8(bitPattern: $0) }, as: UTF8.self)
        }
        return !names.isEmpty && Set(names).isSubset(of: ["com.apple.provenance"])
    }
}

public enum ReleaseIdentityError: Error, CustomStringConvertible {
    case missingMetadata(String)
    case invalidMetadata
    case invalidInfoPlist
    case unsafeBundle(String)

    public var description: String {
        switch self {
        case let .missingMetadata(key): return "release metadata is missing \(key)"
        case .invalidMetadata: return "release metadata is invalid"
        case .invalidInfoPlist: return "release Info.plist is invalid"
        case let .unsafeBundle(path): return "release bundle inventory is unsafe: \(path)"
        }
    }
}

private extension Digest {
    var hex: String {
        map { String(format: "%02x", $0) }.joined()
    }
}
