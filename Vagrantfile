# -*- mode: ruby -*-
# vi: set ft=ruby :

VAGRANTFILE_API_VERSION = "2"

Vagrant.configure(VAGRANTFILE_API_VERSION) do |config|

  config.vm.define "pdbot" do |dev|
    dev.vm.box = "ubuntu/xenial64"
    dev.vm.host_name = "pdbot"
    dev.vm.network :private_network, ip: "10.1.0.3"
    config.vm.provider :virtualbox do |vb|
        vb.customize ["modifyvm", :id, "--memory", "2048"]
        vb.customize ["modifyvm", :id, "--ioapic", "on"]
        vb.customize ["modifyvm", :id, "--cpus", "2"]
        vb.linked_clone = true
    config.vm.synced_folder ".", "/vagrant",
        type: "virtualbox",
        mount_options: ["dmode=775,fmode=775"]
    end
    config.vm.provision "shell", path: "scripts/vagrant_bootstrap.sh"
  end

end
