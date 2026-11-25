pipeline {
  agent any
  stages {
    stage('Hello') {
      steps {
        echo "Jenkins CI 연결 확인: ${env.BRANCH_NAME}"
        sh 'ls -al'
      }
    }
  }
}