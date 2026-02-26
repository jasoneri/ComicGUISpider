use pep440_rs::Version;
use std::str::FromStr;

pub fn normalize_version(version: &str) -> (String, bool) {
    let cleaned = version.trim().trim_start_matches(['v', 'V']);
    match Version::from_str(cleaned) {
        Ok(ver) => (ver.to_string(), ver.is_pre()),
        Err(_) => (cleaned.to_string(), false),
    }
}

pub fn build_install_args(version: &str, index_url: &str, script: bool) -> Vec<String> {
    let (normalized, is_prerelease) = normalize_version(version);
    let package_name = if script {
        "ComicGUISpider[script]"
    } else {
        "ComicGUISpider"
    };
    let mut cmd = vec![
        "tool".into(),
        "install".into(),
        format!("{package_name}=={normalized}"),
    ];

    if !index_url.is_empty() {
        if index_url.starts_with("file://") {
            cmd.extend(["--extra-index-url".into(), index_url.to_string()]);
        } else {
            cmd.extend(["--index-url".into(), index_url.to_string()]);
        }
    }

    if is_prerelease {
        cmd.extend(["--prerelease".into(), "if-necessary-or-explicit".into()]);
    }
    cmd.push("--force".into());
    cmd
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_stable_version() {
        assert_eq!(normalize_version("2.8.6"), ("2.8.6".into(), false));
    }

    #[test]
    fn test_beta_version() {
        assert_eq!(normalize_version("2.8.6b1"), ("2.8.6b1".into(), true));
    }

    #[test]
    fn test_version_with_v_prefix() {
        assert_eq!(normalize_version("v2.8.6-beta1"), ("2.8.6b1".into(), true));
    }

    #[test]
    fn test_alpha_version() {
        assert_eq!(normalize_version("2.9.0-alpha2"), ("2.9.0a2".into(), true));
    }

    #[test]
    fn test_rc_version() {
        assert_eq!(normalize_version("3.0.0-rc"), ("3.0.0rc0".into(), true));
    }

    #[test]
    fn test_build_args_stable() {
        let args = build_install_args("2.8.6", "https://pypi.tuna.tsinghua.edu.cn/simple", false);
        assert!(args.contains(&"ComicGUISpider==2.8.6".to_string()));
        assert!(args.contains(&"--index-url".to_string()));
        assert!(!args.contains(&"--prerelease".to_string()));
    }

    #[test]
    fn test_build_args_prerelease() {
        let args = build_install_args("2.8.6b1", "", false);
        assert!(args.contains(&"ComicGUISpider==2.8.6b1".to_string()));
        let idx = args.iter().position(|a| a == "--prerelease").expect("--prerelease flag missing");
        assert_eq!(args.get(idx + 1).map(String::as_str), Some("if-necessary-or-explicit"));
    }

    #[test]
    fn test_build_args_local_index() {
        let args = build_install_args("2.8.6", "file:///tmp/wheels", false);
        assert!(args.contains(&"--extra-index-url".to_string()));
    }

    #[test]
    fn test_build_args_script() {
        let args = build_install_args("2.8.6", "", true);
        assert!(args.contains(&"ComicGUISpider[script]==2.8.6".to_string()));
    }
}
