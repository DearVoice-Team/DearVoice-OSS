// 빌드한 이미지를 Push 단계에서 다시 쓰려고 밖에 선언
def frontendImage
def backendImage

pipeline {
  agent any

  environment {
    DOCKERHUB_USER = 'dearvoice'
    DOCKERHUB_CREDENTIALS = 'dearvoice-dockerhub'
    FRONTEND_IMAGE = "${DOCKERHUB_USER}/dearvoice-frontend"
    BACKEND_IMAGE = "${DOCKERHUB_USER}/dearvoice-backend"
    VITE_GOOGLE_CLIENT_ID = '528904608748-9hq03fpn83ohs4v6qroojb99nbpor1ql.apps.googleusercontent.com'
  }

  options {
    // VM 사양이 넉넉하지 않아서 빌드는 한 번에 하나씩만
    disableConcurrentBuilds()
    buildDiscarder(logRotator(numToKeepStr: '20'))
  }

  stages {
    stage('Prepare') {
      steps {
        script {
          // 빌드 번호만 쓰면 브랜치마다 번호가 겹쳐서 커밋 해시를 붙임 (예: 12-a1b2c3d)
          env.SHORT_COMMIT = sh(script: 'git rev-parse --short=7 HEAD', returnStdout: true).trim()
          env.IMAGE_TAG = "${env.BUILD_NUMBER}-${env.SHORT_COMMIT}"
        }
        echo "Branch: ${env.BRANCH_NAME}, Image tag: ${env.IMAGE_TAG}"
      }
    }

    stage('Build frontend image') {
      steps {
        script {
          // API 요청은 Ingress가 /api로 넘겨주니까 주소는 비워둠
          frontendImage = docker.build(
            "${FRONTEND_IMAGE}:${IMAGE_TAG}",
            "--build-arg VITE_SERVER_API_URL= --build-arg VITE_GOOGLE_CLIENT_ID=${VITE_GOOGLE_CLIENT_ID} ./frontend/dearvoice"
          )
        }
      }
    }

    stage('Build backend image') {
      steps {
        script {
          backendImage = docker.build("${BACKEND_IMAGE}:${IMAGE_TAG}", "./backend")
        }
      }
    }

    stage('Push images') {
      // PR은 빌드만 확인하고, 리뷰 끝나서 merge된 것만 Docker Hub에 올림
      when {
        anyOf {
          branch 'develop'
          branch 'main'
        }
      }
      steps {
        script {
          docker.withRegistry('https://registry.hub.docker.com', DOCKERHUB_CREDENTIALS) {
            frontendImage.push(IMAGE_TAG)
            frontendImage.push('latest')
            backendImage.push(IMAGE_TAG)
            backendImage.push('latest')
          }
        }
      }
    }
  }

  post {
    always {
      // 빌드할 때마다 남는 중간 이미지 때문에 디스크 차는 거 방지
      sh 'docker image prune -f'
    }
  }
}